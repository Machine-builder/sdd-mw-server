import logging
import uuid
import pickle
import os
import math
from scripts import database
from scripts import utilities
import difflib
import time

class CONST:
    class CHATPERMS:
        # chat permission values
        PARTICIPANT = 0
    class E2ESTEP:
        # e2e setup steps
        NOT_SETUP = 0

CHAT_PAGE_SIZE_DEFAULT = 8

class User:
    def __init__(self):
        # unique identifier for the user
        self.setUuid('NOT_REGISTERED')
        # whether this user has logged in
        self.logged_in = False
        # user's username
        self.username = None
    
    def setUuid(self, provided_uuid=None):
        self.uuid = provided_uuid or uuid.uuid4()
    
    def __repr__(self):
        return f'User<{self.logged_in},{self.uuid},{self.username}>'


class UserManager:
    def __init__(self, user_database):
        self.database = user_database
        self.connected_users = {}

        self.getUserByUUID = self.database.findEntryByUUID
    
    def __repr__(self):
        return f'UserManager<>'
    
    def addConnectedUser(self, conn):
        '''
        Add a new user to the connected users dict
        
        Returns the newly added user
        '''
        new_user = User()
        self.connected_users[conn] = new_user
        return new_user
    
    def getConnectedUser(self, conn):
        '''
        Returns the user for the connection, or None
        '''
        return self.connected_users.get(conn, None)
    
    def getConnByUUID(self, uuid:str):
        for conn, user in self.connected_users.items():
            if user.uuid == uuid:
                return conn
        return None
    
    def iterateConnectedUsers(self, uuids:list):
        """
        Iterate over all users in the uuids list
        as long as they are currently connected
        to the server
        """
        for uuid in uuids:
            print('iter', uuid)
            conn = self.getConnByUUID(uuid)
            if conn == None:
                continue
            yield conn
    

    def searchUsersByUsername(self, query:str, get_max:int):
        '''
        Searches the user database for users
        with usernames similar to the query
        '''
        query = query.lower()
        all_users = self.database.loaded_data['entries']
        users_by_usernames = {user['username'].lower():user for user in all_users}
        all_usernames = list(users_by_usernames.keys())
        resulting_usernames = difflib.get_close_matches(query, all_usernames, n=get_max, cutoff=0.05)
        resulting_users = [users_by_usernames[username] for username in resulting_usernames]
        result = [
            {'uuid': user['uuid'], 'username': user['username']}\
            for user in resulting_users
        ]
        return result
    
    def removeConnectedUser(self, conn):
        '''
        Remove a user from the connected users dict

        Returns the removed user, or None
        '''
        if not conn in self.connected_users:
            return None
        return self.connected_users.pop(conn)
    
    def attemptLogin(self, user, data):
        username = data.username
        password_hash = data.password_hash
        # first find the referenced account, by username
        reference_account = self.database.findEntryByUsername(username)
        if reference_account is None:
            return (False, None)
        # now we can compare password hashes
        if reference_account['password_hash'] == password_hash:
            # login successful
            user.logged_in = True
            user.username = username
            user.uuid = reference_account['uuid']
            return (True, user.uuid)
        else:
            return (False, None)
    
    def attemptSignUp(self, user, data):
        username = data.username
        password_hash = data.password_hash
        # try find a user with the same name
        reference_account = self.database.findEntryByUsername(username)
        if reference_account != None:
            # an account already exists,
            # so the username cannot be used
            return (False, None)
        if user.logged_in:
            # user is already logged in, so
            # how can they be signing up?
            # possibly modified client?
            # TODO ban user
            return (False, None)
        self.database.addUser(username, password_hash)
        reference_account = self.database.findEntryByUsername(username)
        user.logged_in = True
        user.username = username
        user.uuid = reference_account['uuid']
        return (True, user.uuid)



class ChatMessage(object):
    def __init__(
            self,
            content="",
            sender=None,
            timestamp=-1):
        self.content = content
        self.sender = sender
        self.timestamp = timestamp
        if self.timestamp == -1:
            self.timestamp = utilities.Time.getUTCTs()
        
    def toJson(self):
        return {
            'content': self.content,
            'sender': self.sender,
            'timestamp': self.timestamp
        }

class ChatManager(object):
    def __init__(self, chats_database):
        self.database = chats_database
        self.chat_messages = {}
    
    def processMessageJsonBeforeSend(self, messages, chat, user_manager):
        for message in messages:
            # harcoded uuid meaning it's a server message
            if message['sender_uuid'] == 'server':
                message['from_server'] = True
                # process any required text replacements
                if '%[creator]%' in message['content']:
                    creator_uuid = chat['creator_uuid']
                    creator = user_manager.database.findUserByUUID(creator_uuid)
                    creator_name = 'Deleted User'
                    if creator != None: 
                        creator_name = creator['username']
                    replace_with = creator_name
                    message['content'] = message['content'].replace('%[creator]%', replace_with)
    
    def createNewChat(
            self,
            creator_uuid:str,
            chat_uuid:str,
            chat_name:str,
            participants:list):
        
        if chat_uuid == None:
            chat_uuid = str(uuid.uuid4())
        
        messages = self.loadChatMessages(chat_uuid)
        if messages == None:
            messages = []
        self.chat_messages[chat_uuid] = messages

        existing_chat = self.database.getChatByUUID(chat_uuid)
        exists = True
        if existing_chat == None:
            result = self.database.append({
                "creator_uuid": creator_uuid,
                "uuid": chat_uuid,
                "name": chat_name,
                "participants": participants,
                "participants_e2e": [],
                "last_message_ts": utilities.Time.getUTCTs()})
            if not result:
                exists = False
            self.database.modified = True
        
        self.saveChatMessages(chat_uuid)
        self.database.saveData()
        
        if not exists:
            return False
        return chat_uuid
    
    def getChatMessagesFilepath(self, chat_uuid:str):
        return f'./server/chats/{chat_uuid}.msgs'
    
    def loadChatMessages(self, chat_uuid:str):
        """
        Load a chat into temporary storage
        """
        logging.debug(
            f'load chat messages from file, '\
            f'chat uuid {chat_uuid}')
        messages_filepath = self.getChatMessagesFilepath(chat_uuid)
        if os.path.exists(messages_filepath):
            with open(messages_filepath, 'rb') as f:
                messages = pickle.load(f)
        else:
            logging.warn(
                f'error loading chat messages, no file '\
                f'found at {messages_filepath}')
            return None
        self.chat_messages[chat_uuid] = messages
        return self.chat_messages[chat_uuid]
    
    def getChatMessages(self, chat_uuid:str):
        """
        Get the messages list of a chat.
        If the chat is not loaded, this
        function will load it from file.
        If the chat does not exist, this
        function will return None
        """
        if chat_uuid in self.chat_messages:
            return self.chat_messages[chat_uuid]
        else:
            messages = self.loadChatMessages(chat_uuid)
            if messages == False:
                return None
            return messages
    
    def saveChatMessages(self, chat_uuid:str):
        messages_filepath = self.getChatMessagesFilepath(chat_uuid)
        messages = self.getChatMessages(chat_uuid)
        if messages == None:
            return False
        messages_bytes = pickle.dumps(messages)
        with open(messages_filepath, 'wb') as f:
            f.write(messages_bytes)
        self.database.saveIfModified()
    
    def addChatMessage(self, chat_uuid:str, message):
        messages = self.getChatMessages(chat_uuid)
        if messages == None:
            return False
        messages.append(message)
        chat = self.database.getChatByUUID(chat_uuid)
        chat['last_message_ts'] = utilities.Time.getUTCTs()
        self.database.modified = True
        self.saveChatMessages(chat_uuid)
        return message
    
    def getMessagesPage(
            self,
            chat_uuid:str,
            page_index:int,
            page_size:int=CHAT_PAGE_SIZE_DEFAULT):
        """
        Get "page" of messages.
        optional argument page_size
        determines how many messages
        are in each page.
        """
        messages = self.getChatMessages(chat_uuid)
        paginated = utilities.splitIterableIntoChunks(messages, page_size)
        try:
            return paginated[page_index]
        except IndexError:
            return []
    
    def getLastPageIndex(
            self,
            chat_uuid:str,
            page_size:int=CHAT_PAGE_SIZE_DEFAULT):
        messages = self.getChatMessages(chat_uuid)
        return int((len(messages)-1) / page_size)
    
    def addParticipantToChat(self, chat_uuid:str, participant_uuid:str):
        """
        Add a participant to an existing chat
        """
        chat = self.database.getChatByUUID(chat_uuid)
        if chat == None:
            return False
        participants = chat['participants']
        if not participant_uuid in participants:
            participants.append(participant_uuid)
            self.database.modified = True
        return True
        
    def getChatsByParticipant(self, participant_uuid:str):
        """
        Get a list of chats that have
        a specified participant in them
        """
        matching = [chat for chat in self.database.loaded_data['entries']
            if participant_uuid in chat['participants']]
        return matching
    
    def isUserInChat(self, chat_uuid:str, participant_uuid:str):
        chat = self.database.getChatByUUID(chat_uuid)
        if chat == None:
            return False
        participants = chat['participants']
        return participant_uuid in participants
    
    def getChatByUUID(self, chat_uuid:str):
        return self.database.getChatByUUID(chat_uuid)
    
    def getChatParticipants(self, chat_uuid:str):
        chat = self.getChatByUUID(chat_uuid)
        return chat['participants'].copy()
    
    def getParticipantsWithoutE2E(self, chat_uuid:str):
        chat = self.getChatByUUID(chat_uuid)
        if chat == None:
            return []
        return [uuid for uuid in chat['participants'] if not uuid in chat['participants_e2e']]