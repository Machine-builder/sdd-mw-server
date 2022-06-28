from scripts.ebsockets import connections
from scripts.crypto import Asymmetric, DataPacket
from scripts.constants import CONSTANTS
from scripts import database
import logging
import uuid

# ~~~ Client-Side ~~~ #

class ClientsideHandshake(object):
    def __init__(
            self,
            handshake_id:str,
            side:int=CONSTANTS.RECEIVER,
            given_key_pair=None):
        
        self.handshake_id = handshake_id
        self.side = side
        self.step = 0
        self.finished = False
        
        if given_key_pair == None:
            self.Spu = None
            self.Spr = None
        else:
            self.Spu, self.Spr = given_key_pair

        self.executeNextStep()
    
    def executeStep(self, step, **kwargs):
        self.step = step
        return self.executeNextStep(**kwargs)
        
    def executeNextStep(self, **kwargs):
        process_extra_events = []

        if self.side == CONSTANTS.SENDER:
            if self.step == 0:
                if self.Spu == None:
                    self.Spu, self.Spr = Asymmetric.createKeyPair()
                self.shared_key_public = self.Spu
                self.shared_key_private = self.Spr
                self.step = 1
            # receiver has steps between these steps
            elif self.step == 1:
                assert "Rpu" in kwargs
                bRpu = kwargs['Rpu']
                Rpu = Asymmetric.keyFromBytes(
                    bRpu, CONSTANTS.PUBLIC)
                bSpu = Asymmetric.keyToBytes(
                    self.Spu, CONSTANTS.PUBLIC)
                bSpr = Asymmetric.keyToBytes(
                    self.Spr, CONSTANTS.PRIVATE)
                ebSpu_packet = DataPacket(bSpu)
                ebSpr_packet = DataPacket(bSpr)
                ebSpu_packet.encrypt(Rpu)
                ebSpr_packet.encrypt(Rpu)
                self.step = -1
                n_event = connections.ebsocket_event(
                    "E2E_HANDSHAKE",
                    handshake_id=self.handshake_id,
                    action="FINAL_RECV",
                    data={
                        "ebSpu_packet": ebSpu_packet,
                        "ebSpr_packet": ebSpr_packet}
                )
                process_extra_events.append({
                    "action": "send", 
                    "event": n_event
                })
                self.finished = True
        
        elif self.side == CONSTANTS.RECEIVER:
            if self.step == 0:
                # create Rpu, Rpr keys
                self.Rpu, self.Rpr = Asymmetric.createKeyPair()
                self.step = 1
            elif self.step == 1:
                bRpu = Asymmetric.keyToBytes(
                    self.Rpu, CONSTANTS.PUBLIC)
                self.step = 2
                n_event = connections.ebsocket_event(
                    "E2E_HANDSHAKE",
                    handshake_id=self.handshake_id,
                    action="FINAL_SEND",
                    data={"Rpu": bRpu}
                )
                process_extra_events.append({
                    "action": "send", 
                    "event": n_event
                })
            # sender has steps between these steps
            elif self.step == 2:
                assert "ebSpu_packet" in kwargs
                assert "ebSpr_packet" in kwargs
                ebSpu_packet = kwargs['ebSpu_packet']
                ebSpr_packet = kwargs['ebSpr_packet']
                ebSpu_packet.decrypt(self.Rpr)
                ebSpr_packet.decrypt(self.Rpr)
                self.shared_key_public = Asymmetric.keyFromBytes(
                    ebSpu_packet.payload, CONSTANTS.PUBLIC)
                self.shared_key_private = Asymmetric.keyFromBytes(
                    ebSpr_packet.payload, CONSTANTS.PRIVATE)
                self.step = -1
                self.finished = True

        if self.finished:
            process_extra_events.append({
                "action": "save_encryption_keys"
            })

        return process_extra_events

class ClientsideHandshakeManager(object):
    """
    Manages e2e handshakes with other clients
    through the server. Any event == "E2E_HANDSHAKE"
    should be sent through the process() function of
    an instance of this class.
    """
    def __init__(self, database):
        # id: handshake
        self.handshakes = {}
        # encryption_keys should be loaded from
        # a local database
        # id: (public, private)
        self.encryption_keys = {}
        self.database = database
    
    def loadEncryptionKeys(self):
        """
        Load encryption keys from a database.
        Note this function does not tell the
        database to load its data from a file.
        That should be done before this function.
        """
        self.database.loadData()
        for entry in self.database.loaded_data['entries']:
            encryption_key_id = entry['encryption_key_id']
            key_public_bytes = entry['public']
            key_private_bytes = entry['private']
            key_public = Asymmetric.keyFromBytes(
                key_public_bytes, CONSTANTS.PUBLIC
            )
            key_private = Asymmetric.keyFromBytes(
                key_private_bytes, CONSTANTS.PRIVATE
            )
            self.encryption_keys[encryption_key_id] = (
                key_public, key_private
            )
        print(f"loaded {len(self.database.loaded_data['entries'])} key pairs")

    def saveEncryptionKeys(self):
        """
        Save encryption keys to a database.
        Note this function does not tell the
        database to save its data. That should
        be executed separately.
        """
        self.database.loaded_data['entries'] = []
        for encryption_key_id in self.encryption_keys:
            key_public, key_private = self.encryption_keys[encryption_key_id]
            key_public_bytes = Asymmetric.keyToBytes(
                key_public, CONSTANTS.PUBLIC
            )
            key_private_bytes = Asymmetric.keyToBytes(
                key_private, CONSTANTS.PRIVATE
            )
            entry = {
                "encryption_key_id": encryption_key_id,
                "public": key_public_bytes,
                "private": key_private_bytes
            }
            self.database.loaded_data['entries'].append(entry)
        self.database.saveData()
        print(f"saved {len(self.database.loaded_data['entries'])} key pairs")
    
    def createKeyPair(self, encryption_key_id:str):
        if encryption_key_id in self.encryption_keys:
            return False
        pu, pr = Asymmetric.createKeyPair()
        pair = (pu, pr)
        self.encryption_keys[encryption_key_id] = pair
        del(pu, pr)
        self.saveEncryptionKeys()
        return True
    
    def process(self, event):
        process_extra_events = []
        handshake_id = event.handshake_id
        encryption_key_id = handshake_id.split('+',1)[0]
        action = event.action

        if action == "INIT_SEND":
            logging.debug(f"init_send event, creating handshake "\
                f"to track process, handshake id {handshake_id}")
            if not encryption_key_id in self.encryption_keys:
                # there are no encryption keys for this
                # id just yet, so create a new entry and keys
                logging.warn(f"no existing encryption key found for handshake, "\
                    "so creating new key pair")
                pu, pr = Asymmetric.createKeyPair()
                pair = (pu, pr)
                self.encryption_keys[encryption_key_id] = pair
                del(pu, pr)
            else:
                logging.debug(f"existing encryption key found for handshake")
            handshake = ClientsideHandshake(
                handshake_id,
                CONSTANTS.SENDER,
                self.encryption_keys[encryption_key_id]
            )
            self.handshakes[handshake_id] = handshake

        elif action == "INIT_RECV":
            logging.debug(f"init_recv event, creating handshake "\
                f"to track process, handshake id {handshake_id}")
            handshake = ClientsideHandshake(
                handshake_id,
                CONSTANTS.RECEIVER
            )
            self.handshakes[handshake_id] = handshake
            if encryption_key_id in self.encryption_keys:
                logging.debug(f"encryption key id is already saved, "\
                    f"but a new handshake was initiated so its value "\
                    f"has been cleared for overwrite")
            self.encryption_keys[encryption_key_id] = (
                None, None)
            result = handshake.executeStep(1)
            process_extra_events.extend(result)

        elif action == "FINAL_SEND":
            handshake = self.handshakes.get(handshake_id, None)
            if handshake is None:
                logging.warn(f"final_send event could not find "\
                    f"handshake with id {handshake_id}, ignoring event")
                return process_extra_events
            data = event.data
            result = handshake.executeStep(1, **data)
            process_extra_events.extend(result)
            logging.debug(f"final_send completed, handshake id {handshake_id}")

        elif action == "FINAL_RECV":
            handshake = self.handshakes.get(handshake_id, None)
            if handshake is None:
                logging.warn(f"final_recv event could not find "\
                    f"handshake with id {handshake_id}, ignoring event")
                return process_extra_events
            data = event.data
            result = handshake.executeStep(2, **data)
            process_extra_events.extend(result)
            self.encryption_keys[encryption_key_id] = (
                handshake.shared_key_public,
                handshake.shared_key_private
            )
            logging.debug(f"final_recv completed, handshake id {handshake_id}")
        
        return process_extra_events

# ~~~ Server-Side ~~~ #

class SingleHandshakeManager(object):
    def __init__(
            self,
            conn_sender,
            conn_receiver,
            handshake_id:str):
        self.conn_sender = conn_sender
        self.conn_receiver = conn_receiver
        self.handshake_id = handshake_id
        self.initiated = False
    
    def initiate(self):
        """
        Sends both users an event which tells
        them to begin the handshake process
        """
        process_extra_events = []
        # create and send the event that will
        # tell the receiver to begin the process
        n_event = connections.ebsocket_event(
            "E2E_HANDSHAKE",
            handshake_id=self.handshake_id,
            action="INIT_RECV")
        process_extra_events.append({
            "action": "send",
            "event": n_event,
            "to": self.conn_receiver})
        # create and send the event that will
        # tell the sender to begin the process
        n_event = connections.ebsocket_event(
            "E2E_HANDSHAKE",
            handshake_id=self.handshake_id,
            action="INIT_SEND")
        process_extra_events.append({
            "action": "send",
            "event": n_event,
            "to": self.conn_sender})
        self.initiated = True
        return process_extra_events
    
    def processEvent(self, event):
        """
        Process a single event in the
        handshake process
        """
        process_extra_events = []
        action = event.action
        if action == "FINAL_SEND":
            # this event is sent from the
            # receiver connection, to the server,
            # to the sender connection
            assert event.from_connection == self.conn_receiver
            data = event.data
            n_event = connections.ebsocket_event(
                "E2E_HANDSHAKE",
                handshake_id=self.handshake_id,
                action="FINAL_SEND",
                data=data)
            process_extra_events.append({
                "action": "send",
                "event": n_event,
                "to": self.conn_sender})
        elif action == "FINAL_RECV":
            # this event is sent from the
            # sender connection, to the server,
            # to the receiver connection
            assert event.from_connection == self.conn_sender
            data = event.data
            n_event = connections.ebsocket_event(
                "E2E_HANDSHAKE",
                handshake_id=self.handshake_id,
                action="FINAL_RECV",
                data=data)
            process_extra_events.append({
                "action": "send",
                "event": n_event,
                "to": self.conn_receiver})
            process_extra_events.append({
                'action': 'handshake_complete',
                'handshake_id': self.handshake_id,
                'conn_sender': self.conn_sender,
                'conn_receiver': self.conn_receiver
            })
        return process_extra_events
    
class HandshakeManager(object):
    def __init__(self):
        # dict containing id: handshake pairs
        # for easy access and reference
        self.handshakes = {}
        self.waiting_for_init = []
    
    def createHandshake(
            self,
            conn_sender,
            conn_receiver,
            handshake_id:str=''):
        """
        Create a new handshake between
        two connections (users)

        if handshake_id is not provided,
        handshake_id will be a random uuid4+tag.
        """
        # if the handshake id isn't provided
        # it should be automatically set as
        # a uuid4
        if len(handshake_id) == 0:
            # handshake_id should actually be the id
            # of the chat (or other e2e thing), with
            # an added tag
            # <uuid>+00 (or 01, 02, so on)
            handshake_id = str(uuid.uuid4())
            # some set ID, representing a chat uuid
        handshake_id_start = handshake_id
        tag = 0
        valid = False
        while not valid:
            # keep adding +1 to tag until
            # it is an id that isn't already used
            tag += 1
            tag_str = str(tag).rjust(4, '0')
            handshake_id = handshake_id_start+'+'+tag_str
            if not handshake_id in self.handshakes:
                valid = True
        # create a new class instance to
        # manage this handshake, and then
        # save the class to the dict.
        # also "mark" this instance as one
        # that requires initialisation
        handshake = SingleHandshakeManager(
            conn_sender, conn_receiver, handshake_id)
        self.handshakes[handshake_id] = handshake
        self.waiting_for_init.append(handshake_id)
        return True
    
    def getHandshakeById(self, handshake_id:str):
        """
        Tries to find an existing handshake
        with a provided ID. If none exist, the
        function returns None
        """
        # use the dict.get() function to try find
        # the provided key, otherwise None
        handshake = self.handshakes.get(handshake_id, None)
        return handshake
    
    def process(self, event):
        # create a list to store any events
        # that need sending later on
        process_extra_events = []

        # process this handshake step
        handshake_id = event.handshake_id
        handshake = self.getHandshakeById(handshake_id)
        process_extra_events.extend(handshake.processEvent(event))
    
        return process_extra_events
    
    def checkForUpdates(self):
        process_extra_events = []
        # check for any handshakes waiting
        # to be initialised, and if there are
        # any then trigger the initialisation
        for handshake_id in self.waiting_for_init:
            handshake = self.getHandshakeById(handshake_id)
            process_extra_events.extend(handshake.initiate())
        self.waiting_for_init = []
        return process_extra_events