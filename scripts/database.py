import json
import pickle

from scripts import crypto
from scripts import utilities

import uuid

class DatabaseUtil:
    @staticmethod
    def matchEntryToStructure(entry, structure):
        # get all keys and values in the provided entry
        for key in entry:
            value = entry[key]
            value_type = type(value)
            s_value = structure.get(key, -1)
            s_value_type = type(s_value)
            # print('vt', value_type, s_value_type)
            if s_value == -1:
                return False
            if s_value_type == tuple:
                # s_value is something like (int, float)
                # in which case the entry can be either type
                if not value_type in s_value:
                    return False
            elif s_value_type == type:
                if not value_type == s_value:
                    # print('not value_type == s_value')
                    return False
        return True

class Database:
    """
    Base-class database

    Supports searching for entries based on
    provided field.
    """
    def __init__(
            self,
            filename:str=None,
            entry_structure:dict=None,
            load_immediately:bool=True
        ):
        self.filename = filename
        self.entry_structure = entry_structure
        self.valid_fields = []

        if load_immediately:
            self.loadData()
    
    def saveData(self):
        with open(self.filename, 'w') as f:
            json.dump(self.loaded_data, f)
        return True
    
    def _loadDataGetFile(self):
        with open(self.filename, 'r') as f:
            self.loaded_data = json.load(f)
    
    def loadData(self):
        if self.filename == None:
            self.loaded_data = {'entries': []}
            return None
        self._loadDataGetFile()
        self.valid_fields = []
        for entry in self.loaded_data['entries']:
            for field in entry:
                if not field in self.valid_fields:
                    self.valid_fields.append(field)
        return True
    
    def append(self, entry):
        """appends a new entry to the database"""
        is_valid = DatabaseUtil.matchEntryToStructure(
            entry, self.entry_structure)
        if not is_valid:
            return False
        self.loaded_data['entries'].append(entry)
        return True
    
    def findEntryByField(self, field, value, validate_field=False, match_case=True):
        if validate_field and (not field in self.valid_fields):
            return None
        if match_case:
            for entry in self.loaded_data['entries']:
                if entry.get(field, None) == value:
                    return entry
        else:
            value_lower = value.lower()
            for entry in self.loaded_data['entries']:
                entry_value = entry.get(field, None)
                if entry_value == None: continue
                if entry_value.lower() == value_lower:
                    return entry
        return None

class EncryptedDatabase(Database):
    def __init__(self, *args, **kwargs):
        self.key = kwargs.pop('key')
        kwargs['load_immediately'] = False
        super().__init__(*args, **kwargs)
        try:
            self.loadData()
        except FileNotFoundError:
            old_filename = self.filename
            self.filename = None
            self.loadData()
            self.filename = old_filename
            self.saveData()

    def saveData(self):
        # overwrite the original function
        f_data = pickle.dumps(self.loaded_data)
        # write_data is bytes object so we can
        # encrypt it using the crypto module
        f_data_encrypted = crypto.Symmetric.encryptBytes(f_data, self.key)
        f_data_chunks = utilities.splitStringIntoChunks(f_data_encrypted, 64)
        f_data_encrypted = b'\n'.join(f_data_chunks)
        with open(self.filename, 'wb') as f:
            f.write(f_data_encrypted)
        return True
    
    def _loadDataGetFile(self):
        with open(self.filename, 'rb') as f:
            f_data_encrypted = f.read()
        f_data_encrypted = f_data_encrypted.replace(b'\n', b'')
        f_data = crypto.Symmetric.decryptBytes(f_data_encrypted, self.key)
        self.loaded_data = pickle.loads(f_data)
        return True
        

class UserDatabase(Database):
    def __init__(self, *args, **kwargs):
        kwargs["entry_structure"] = {
            "username": str,
            "password_hash": str,
            "uuid": str
        }
        super().__init__(*args, **kwargs)
        self.findUserByUUID = self.findEntryByUUID
    
    def addUser(self, username:str, password_hash:str):
        entry = {
            'username': username,
            'password_hash': password_hash,
            'uuid': str(uuid.uuid4())
        }
        self.append(entry)
        self.saveData()
        
    def findEntryByUsername(self, username):
        print(self.loaded_data['entries'])
        return self.findEntryByField('username', username, match_case=False)
        
    def findEntryByUUID(self, uuid):
        return self.findEntryByField('uuid', uuid)

class ChatDatabase(Database):
    def __init__(self, *args, **kwargs):
        kwargs["entry_structure"] = {
            "creator_uuid": str,
            # the chat's unique identifier
            "uuid": str,
            # the chat's name, shown to users
            "name": str,
            # the list of user uuids of each
            # participant
            "participants": list,
            "participants_e2e": list,
            # the timestamp of the last message
            # sent, so that chats can be ordered
            # by date for users
            "last_message_ts": int
        }
        # the messages in a chat are stored
        # within the chat's individual data file
        # (for storage size reasons -
        #  overflow protection)
        super().__init__(*args, **kwargs)
        self.modified = False
    
    def getChatByUUID(self, uuid):
        return self.findEntryByField('uuid', uuid)
    
    def saveIfModified(self):
        if self.modified:
            self.saveData()
        self.modified = False