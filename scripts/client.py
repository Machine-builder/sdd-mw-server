import logging

from .ebsockets.connections import ebsocket_client, ebsocket_event
from .passwords import get_password_hash
from scripts import e2e_handshakes, utilities
from scripts import database
from scripts import unique_pc_identifier
from scripts.crypto import Symmetric, Asymmetric, Hybrid, DataPacket

class Client(object):
    def __init__(self, backend):
        # keep a reference to the backend object
        # so that this class instance can call functions
        self.backend = backend
        self.eb_client = ebsocket_client()
        self.unique_sym_key = unique_pc_identifier.getUniqueSymmetricKey()
        self.key_database = database.EncryptedDatabase(
            filename="./resources/data/stored_keys.db",
            key=self.unique_sym_key)
        self.handshake_manager = e2e_handshakes.ClientsideHandshakeManager(self.key_database)
        self.handshake_manager.loadEncryptionKeys()
        self.uuid = None
    
    def connectToServer(self, address):
        self.eb_client.connect_to(address)
    
    def attemptSignUp(self, username, password):
        self.attemptLogin(username, password, 'SIGN_UP')
    
    def attemptLogin(self, username, password, method='LOGIN'):
        password_hash = get_password_hash(password)
        n_event = ebsocket_event(
            'ATTEMPT_'+method,
            username=username,
            password_hash=password_hash)
        self.eb_client.send_event(n_event)
    
    def encryptTextToPacket(self, text, encryption_key_id):
        if not encryption_key_id in self.handshake_manager.encryption_keys:
            return None
        k_public, k_private = self.handshake_manager.encryption_keys[encryption_key_id]
        packet = DataPacket(text.encode())
        packet.encrypt(k_public)
        del(k_public, k_private)
        return packet
    
    def decryptPacketToText(self, packet:DataPacket, encryption_key_id):
        if not encryption_key_id in self.handshake_manager.encryption_keys:
            return None
        k_public, k_private = self.handshake_manager.encryption_keys[encryption_key_id]
        failed = False
        try:
            packet.decrypt(k_private)
        except:
            failed = True
        del(k_public, k_private)
        if failed:
            return None
        return packet.payload.decode()
    
    def requestLoadChatsList(self):
        """
        Initiate a request with the server to get
        all of the chat uuids (and names) that
        this user participates in
        """
        n_event = ebsocket_event("REQUEST_CHATS_LIST")
        self.eb_client.send_event(n_event)
    
    def requestGetInitialMessages(self, chat_uuid:str):
        """
        Initiate a request with the server to get
        initial messages for a chat, and the chat
        messages page index
        """
        n_event = ebsocket_event("REQUEST_INITIAL_MESSAGES",
            chat_uuid=chat_uuid)
        self.eb_client.send_event(n_event)
    
    def requestGetMessages(self, chat_uuid:str, messages_page:int):
        """
        Initiate a request with the server to get
        a page of messages for a chat
        """
        n_event = ebsocket_event("REQUEST_GET_MESSAGES",
            chat_uuid=chat_uuid, messages_page=messages_page)
        self.eb_client.send_event(n_event)
    
    def requestSendMessage(self, chat_uuid:str, content:str):
        """
        Initiate a request with the server to send
        a message from one client to others
        """
        encryption_key_id = 'c_'+chat_uuid
        packet = self.encryptTextToPacket(content, encryption_key_id)
        if packet == None:
            # encryption of text failed, possibly missing enc key?
            logging.warn(f'encrypting message to send failed. Maybe missing encryption key?')
            return
        n_event = ebsocket_event("REQUEST_SEND_MESSAGE",
            chat_uuid=chat_uuid, message_content=packet)
        self.eb_client.send_event(n_event)
    
    def requestSearchForUsers(self, query:str, get_max:int, result_action:str):
        """
        Initiate a request with the server to search
        for users by username
        """
        n_event = ebsocket_event("REQUEST_SEARCH_FOR_USERS",
            query=query, get_max=get_max, result_action=result_action)
        self.eb_client.send_event(n_event)
    
    def requestCreateChat(self, chat_name:str, participants:list):
        n_event = ebsocket_event("REQUEST_CREATE_CHAT",
            chat_name=chat_name, participants=participants)
        self.eb_client.send_event(n_event)

    def processServerEvent(self, event):
        """
        Process an event sent from the server
        """
        process_extra_events = []

        if event.event == 'LOGIN_RESULT':
            success = event.success
            if success:
                self.backend.eventLoginSuccess()
                self.uuid = event.uuid
            else:
                self.backend.eventLoginFail()
        elif event.event == 'SIGN_UP_RESULT':
            success = event.success
            if success:
                self.backend.eventSignUpSuccess()
                self.uuid = event.uuid
            else:
                self.backend.eventSignUpFail()
        
        elif event.event == 'REQUEST_CHATS_LIST_FILLED':
            chats = event.chats
            self.backend.requestLoadChatsListFilled(chats)
            for chat_data in chats:
                process_extra_events.append({
                    "action": "check_chat_e2e_keys",
                    "chat_data": chat_data})
        elif event.event == 'NEW_CHAT_CREATED':
            chat_data = event.chat_data
            self.backend.newChatCreated(chat_data)
            process_extra_events.append({
                "action": "check_chat_e2e_keys",
                "chat_data": chat_data})
        
        elif event.event == 'REQUEST_INITIAL_MESSAGES_FILLED':
            messages = event.messages
            self.preprocessMessages(messages, event.chat_uuid)
            self.backend.requestGetInitialMessagesFilled({
                "initial": True,
                "chat_uuid": event.chat_uuid,
                'loaded_to_page': event.loaded_to_page,
                "messages": messages})
        elif event.event == 'REQUEST_GET_MESSAGES_FILLED':
            messages = event.messages
            self.preprocessMessages(messages, event.chat_uuid)
            self.backend.requestGetMessagesFilled({
                "initial": False,
                "chat_uuid": event.chat_uuid,
                'loaded_to_page': event.loaded_to_page,
                "messages": messages})
        
        elif event.event == 'REQUEST_SEND_MESSAGE_FILLED':
            print("Client detected event forwarded from server by other client.")
            messages = [event.message]
            self.preprocessMessages(messages, event.chat_uuid)
            self.backend.requestGetMessagesFilled({
                "initial": False,
                "requested": False,
                "is_new": True,
                "chat_uuid": event.chat_uuid,
                'loaded_to_page': event.loaded_to_page,
                "messages": messages})
            
        elif event.event == 'REQUEST_SEARCH_FOR_USERS_FILLED':
            self.backend.requestSearchForUsersFilled({
                'results': event.results,
                'result_action': event.result_action})
        
        elif event.event == 'CREATE_NEW_KEYS':
            encryption_key_id = event.encryption_key_id
            self.handshake_manager.createKeyPair(encryption_key_id)

        elif event.event == 'E2E_HANDSHAKE':
            result = self.handshake_manager.process(event)
            process_extra_events.extend(result)
        # process any extra events that were created by
        # the above events
        for event in process_extra_events:
            action = event['action']
            if action == 'send':
                self.eb_client.send_event(event['event'])
            elif action == 'save_encryption_keys':
                self.handshake_manager.saveEncryptionKeys()
            elif action == 'check_chat_e2e_keys':
                chat_data = event['chat_data']
                chat_uuid = chat_data['uuid']
                key_id = 'c_'+chat_uuid
                logging.debug(f'checking encryption keys for id {key_id}...')
                print('check key', key_id)
                if not key_id in self.handshake_manager.encryption_keys:
                    # key does not exist
                    logging.debug(f'no keys found. Requesting handshake with server.')
                    print('no keys?')
                    n_event = ebsocket_event("REQUEST_MISSING_KEYS",
                        chat_uuid=chat_uuid)
                    self.eb_client.send_event(n_event)
                else:
                    logging.debug('keys found')

    def preprocessMessages(self, messages:list, chat_uuid:str):
        # convert timestamps into text
        for message in messages:
            # get local message time
            timestamp = message['timestamp']
            datetime = utilities.Time.UTCToLocal(timestamp)
            message['time_str'] = str(datetime)

            # decrypt message content here too!
            # only decrypt if not from server?
            content_type = type(message['content'])
            print("preprocessMessages -> type(message['content']) =", content_type)
            if content_type == DataPacket:
                encryption_key_id = 'c_'+chat_uuid
                print('processing DataPacket message content')
                packet = message['content']
                content_text = self.decryptPacketToText(packet, encryption_key_id)
                if content_text == None:
                    message['content'] = '???'
                else:
                    message['content'] = content_text
