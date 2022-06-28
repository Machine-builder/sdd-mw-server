from concurrent.futures import process
import logging

logging.basicConfig(
    filename='server.log', filemode='w',
    format='%(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG)

from scripts.ebsockets.connections import (ebsocket_client, ebsocket_event,
                                   ebsocket_server, ebsocket_system)
from scripts.ebsockets.connections import utility as ebsockets_utility
from scripts import passwords
from server import datatypes
from scripts import database
from scripts import e2e_handshakes
from scripts.crypto import DataPacket

local_ip = ebsockets_utility.get_local_ip()
server_addr = (local_ip, 9365)
server = ebsocket_server(server_addr)
system = ebsocket_system(server)

user_manager = datatypes.UserManager(
    user_database=database.UserDatabase('./server/users.db'))
chats_manager = datatypes.ChatManager(
    chats_database=database.ChatDatabase('./server/chats.db'))
e2e_handshake_manager = e2e_handshakes.HandshakeManager()
e2e_pending_chats = []

users = []

def serverMain():
    process_extra_events = []

    n_clients, n_events, d_clients = system.pump()
    process_extra_events.extend(e2e_handshake_manager.checkForUpdates())

    for client in n_clients:
        conn, addr = client
        users.append(conn)
        user_instance = user_manager.addConnectedUser(conn)
        logging.debug(f"client connected to server, client ip : {addr[0]}")
    
    for event in n_events:
        print(f"~~~ event received ~~~")
        print(f"    event: {event}")
        conn = event.from_connection
        user_instance = user_manager.getConnectedUser(conn)
        user_uuid = user_instance.uuid
        print(f"    from user: {user_instance}")

        # if login or sign-up attempt is successful,
        # find the User class in the user_manager that
        # is linked to this connection, and set the uuid
        # to the uuid of the targetted account

        if event.event == 'ATTEMPT_LOGIN':
            success, user_uuid = user_manager.attemptLogin(user_instance, event)
            if not success:
                # user was not able to login,
                # maybe wrong password, maybe wrong username
                n_event = ebsocket_event('LOGIN_RESULT', success=False, uuid=None)
                system.send_event_to(conn, n_event)
            else:
                n_event = ebsocket_event('LOGIN_RESULT', success=True, uuid=user_uuid)
                system.send_event_to(conn, n_event)
                process_extra_events.append({
                    'action': 'check_e2e_on_login',
                    'user_uuid': user_uuid})
    
        elif event.event == 'ATTEMPT_SIGN_UP':
            success, user_uuid = user_manager.attemptSignUp(user_instance, event)
            if not success:
                # user was not able to login,
                # maybe wrong password, maybe wrong username
                n_event = ebsocket_event('SIGN_UP_RESULT', success=False, uuid=None)
                system.send_event_to(conn, n_event)
            else:
                n_event = ebsocket_event('SIGN_UP_RESULT', success=True, uuid=user_uuid)
                system.send_event_to(conn, n_event)
                process_extra_events.append({
                    'action': 'check_e2e_on_login',
                    'user_uuid': user_uuid})
        
        elif event.event == 'E2E_HANDSHAKE':
            # process the on-going handshake
            result = e2e_handshake_manager.process(event)
            process_extra_events.extend(result)
        
        # all of the following events require the user to be
        # logged in, so if they're not, ignore the rest
        # of the events
        if not user_instance.logged_in:
            # user isn't logged in, so ignore the request
            continue
        
        if event.event == 'REQUEST_CHATS_LIST':
            chats = chats_manager.getChatsByParticipant(user_uuid)
            # create a list that contains only the chat information
            # that the user needs to know- Don't send over the
            # participant list unless required, to save bandwidth
            send_list = []
            for chat in sorted(chats, key=lambda chat: chat['last_message_ts'], reverse=True):
                chat_data = {
                    'uuid': chat['uuid'],
                    'name': chat['name']}
                send_list.append(chat_data)
            n_event = ebsocket_event(
                'REQUEST_CHATS_LIST_FILLED',
                chats=send_list)
            system.send_event_to(conn, n_event)
        
        elif event.event == 'REQUEST_CREATE_CHAT':
            chat_name = event.chat_name
            participants = event.participants
            participants.append(user_uuid)
            creator_uuid = user_uuid
            chat_uuid = chats_manager.createNewChat(creator_uuid, None, chat_name, participants)
            logging.debug(f'creating chat, uuid {chat_uuid}, creator uuid {creator_uuid}, chat name "{chat_name}"')
            if chat_uuid == False:
                logging.warn('error creating chat')
                continue
            chats_manager.addChatMessage(
                chat_uuid,
                datatypes.ChatMessage(r"%[creator]% started a new chat", "server"))
            # send an event to all participants in the chat
            # to update their chat lists and show this new chat
            n_event = ebsocket_event(
                'NEW_CHAT_CREATED',
                chat_data={
                    'uuid': chat_uuid,
                    'name': chat_name
                }
            )
            for conn_other in user_manager.iterateConnectedUsers(participants):
                print('send event to', conn_other)
                system.send_event_to(conn_other, n_event)
            # tell the creator of the chat to create a key pair
            n_event = ebsocket_event('CREATE_NEW_KEYS', encryption_key_id='c_'+chat_uuid)
            system.send_event_to(conn, n_event)
            chat = chats_manager.getChatByUUID(chat_uuid)
            chat['participants_e2e'].append(user_uuid)
            chats_manager.database.saveData()
        
        elif event.event in (
                'REQUEST_INITIAL_MESSAGES',
                'REQUEST_GET_MESSAGES'):
            chat_uuid = event.chat_uuid
            if not chats_manager.isUserInChat(chat_uuid, user_uuid):
                # the user isn't even in this chat,
                # and since they sent this event
                # their account may be compromised?
                # TODO in future mark as suspicious activity?
                continue
            chat = chats_manager.getChatByUUID(chat_uuid)
            combined_messages = []
            if event.event == 'REQUEST_INITIAL_MESSAGES':
                last_page_index = chats_manager.getLastPageIndex(chat_uuid)
                lowest_page_index = last_page_index
                pages_sent = 0
                for offset in range(2, -1, -1):
                    page_index = last_page_index - offset
                    if page_index < 0:
                        continue
                    if page_index < lowest_page_index:
                        lowest_page_index = page_index
                    pages_sent += 1
                    messages = chats_manager.getMessagesPage(
                        chat_uuid, page_index)
                    combined_messages.extend(messages)
            elif event.event == 'REQUEST_GET_MESSAGES':
                page_index = event.messages_page
                messages = chats_manager.getMessagesPage(
                    chat_uuid, page_index)
                combined_messages.extend(messages)
                lowest_page_index = page_index
            
            sender_names = {}
            messages = []
            for message in combined_messages:
                sender_uuid = message.sender
                sender_name = sender_names.get(sender_uuid, None)
                if sender_name == None:
                    sender_user = user_manager.getUserByUUID(sender_uuid)
                    if sender_user == None:
                        sender_name = 'UNKNOWN'
                    else:
                        sender_name = sender_user['username']
                message_json = {
                    "content": message.content,
                    "sender_uuid": sender_uuid,
                    "sender_name": sender_name,
                    "timestamp": message.timestamp,
                    "is_own": sender_uuid == user_uuid
                }
                messages.append(message_json)
            chats_manager.processMessageJsonBeforeSend(messages, chat, user_manager)
            n_event = ebsocket_event(
                event.event+'_FILLED',
                chat_uuid=chat_uuid,
                loaded_to_page=lowest_page_index,
                messages=messages)
            system.send_event_to(conn, n_event)
        
        elif event.event == 'REQUEST_SEND_MESSAGE':
            chat_uuid = event.chat_uuid
            if not chats_manager.isUserInChat(chat_uuid, user_uuid):
                continue
            content = event.message_content
            # content is either a string or a DataPacket instance
            message = chats_manager.addChatMessage(
                chat_uuid,
                datatypes.ChatMessage(
                    content=content,
                    sender=user_uuid
                ))
            if not message:
                continue
            chats_manager.saveChatMessages(chat_uuid)
            chat = chats_manager.getChatByUUID(chat_uuid)

            # forward message to other clients
            participants = chats_manager.getChatParticipants(chat_uuid)
            page_index = chats_manager.getLastPageIndex(chat_uuid)

            for conn_other in user_manager.iterateConnectedUsers(participants):
                message_json = {
                    "content": message.content,
                    "sender_uuid": message.sender,
                    "sender_name": user_instance.username,
                    "timestamp": message.timestamp,
                    "is_own": conn == conn_other}
                messages = [message_json]
                chats_manager.processMessageJsonBeforeSend(messages, chat, user_manager)
                message_json = messages[0]
                n_event = ebsocket_event(
                    'REQUEST_SEND_MESSAGE_FILLED',
                    chat_uuid=chat_uuid,
                    loaded_to_page=page_index,
                    message=message_json)
                system.send_event_to(conn_other, n_event)
                print("Forwarding chat event to", conn_other)
        
        elif event.event == 'REQUEST_SEARCH_FOR_USERS':
            query = event.query
            get_max = event.get_max
            result_action = event.result_action
            users_found = user_manager.searchUsersByUsername(query, get_max)
            n_event = ebsocket_event(
                'REQUEST_SEARCH_FOR_USERS_FILLED',
                results=users_found,
                result_action=result_action)
            system.send_event_to(conn, n_event)
        
        if event.event == 'REQUEST_MISSING_KEYS':
            # a user is in a chat but does not have the encryption
            # keys for the chat, so mark them as "requiring" them.
            chat_uuid = event.chat_uuid
            chat = chats_manager.getChatByUUID(chat_uuid)
            if chat == None:
                continue
            participants = chat['participants']
            if not user_uuid in participants:
                continue
            participants_e2e = chat['participants_e2e']
            if user_uuid in participants_e2e:
                participants_e2e.remove(user_uuid)
            process_extra_events.append({
                'action': 'check_e2e',
                'chat_uuid': chat_uuid
            })

    
    for client in d_clients:
        user_instance = user_manager.removeConnectedUser(client[0])
        logging.debug(f"client disconnected from server, client ip : {client[1][0]}")
    
    while len(process_extra_events) > 0:
        event = process_extra_events.pop(0)
        action = event['action']
        if action == 'send':
            to = event.get('to', None)
            if to != None:
                system.send_event_to(to, event['event'])
            else:
                server.send_event(event['event'])
            
        elif action == 'check_e2e_on_login':
            logging.debug('checking uuid on login for e2e chats')
            user_uuid = event['user_uuid']
            chats = chats_manager.getChatsByParticipant(user_uuid)
            pending_chat_uuids = [
                chat['uuid'] for chat in chats if\
                chat['uuid'] in e2e_pending_chats]
            if len(pending_chat_uuids) < 1:
                continue
            logging.debug("at least one chat found pending")
            for chat_uuid in pending_chat_uuids:
                # really only process if this user is a participant with e2e already..?
                # TODO
                process_extra_events.append({
                    'action': 'check_e2e',
                    'chat_uuid': chat_uuid
                })
        
        elif action == 'check_e2e':
            chat_uuid = event['chat_uuid']
            logging.debug(f'check e2e {chat_uuid}')
            if chat_uuid in e2e_pending_chats:
                logging.debug('reason for check: pending chat')
                e2e_pending_chats.remove(chat_uuid)
            encryption_key_id = 'c_'+chat_uuid
            chat = chats_manager.getChatByUUID(chat_uuid)
            participants = chat['participants']
            participants_e2e = chat['participants_e2e']
            logging.debug('participants')
            logging.debug(','.join(participants))
            logging.debug('participants_e2e')
            logging.debug(','.join(participants_e2e))
            requires_key_transfer = False
            for uuid in participants:
                if not uuid in participants_e2e:
                    requires_key_transfer = True
                    break
            if not requires_key_transfer:
                print("there are no users requiring a key")
                continue
            # at least one user requires a key to be sent
            participants_requiring_key = chats_manager.getParticipantsWithoutE2E(chat_uuid)
            logging.debug('list of participant uuids requiring keys:')
            logging.debug(','.join(participants_requiring_key))
            conn_sender = None
            for uuid in participants_e2e:
                conn_other = user_manager.getConnByUUID(uuid)
                if conn_other == None:
                    continue
                conn_sender = conn_other
                break
            if conn_sender == None:
                # there are no online users with the e2e keys,
                # so there's nothing to do for this client
                # until one of them comes online
                logging.debug('there is no user online with a key.')
                logging.debug('adding chat uuid to pending list.')
                e2e_pending_chats.append(chat_uuid)
                continue
            conns_requiring_key = []
            for uuid in participants_requiring_key:
                conn_other = user_manager.getConnByUUID(uuid)
                if conn_other == None:
                    continue
                conns_requiring_key.append(conn_other)
            for conn_receiver in conns_requiring_key:
                e2e_handshake_manager.createHandshake(
                    conn_sender,
                    conn_receiver,
                    encryption_key_id)
                print('created handshake between', conn_sender, 'and', conn_receiver, 'id:', encryption_key_id)
        
        elif action == 'handshake_complete':
            # called when a handshake between two clients is completed
            # when this is done, we know both clients now have keys to
            # the chat
            handshake_id = event['handshake_id']
            logging.debug(f'handshake was completed, handshake id {handshake_id}')
            chat_uuid = handshake_id[2:].split('+',1)[0]
            logging.debug(f'chat uuid from handshake id {chat_uuid}')
            conn_sender = event['conn_sender']
            conn_receiver = event['conn_receiver']
            user_sender = user_manager.getConnectedUser(conn_sender)
            user_receiver = user_manager.getConnectedUser(conn_receiver)
            process_users = [user_sender, user_receiver]
            process_uuids = []
            for user in process_users:
                if user == None:
                    break
                uuid = user.uuid
                process_uuids.append(uuid)
            logging.debug(f'processing uuids [{",".join(process_uuids)}]')
            chat = chats_manager.getChatByUUID(chat_uuid)
            for uuid in process_uuids:
                if not uuid in chat['participants_e2e']:
                    logging.debug(f'added {uuid} to participants_e2e')
                    chat['participants_e2e'].append(uuid)
            if chat_uuid in e2e_pending_chats:
                logging.debug(f'this chat is marked as pending. Checking if reasonable...')
                participants_requiring_key = chats_manager.getParticipantsWithoutE2E(chat_uuid)
                if len(participants_requiring_key) == 0:
                    logging.debug('unreasonable. Unmarking chat as pending e2e.')
                    e2e_pending_chats.remove(chat_uuid)
                else:
                    logging.debug("reasonable. Leaving chat marked as pending e2e.")

print("Server running!")
print(server_addr)
while True:
    # the main loop that does the cool things!
    serverMain()