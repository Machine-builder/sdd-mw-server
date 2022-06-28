from enum import unique
import subprocess
import uuid
from scripts import crypto

class uniquePCIdentifier(object):
    def __init__(self):
        """
        A class used to generate a unique ID
        for any given pc.

        simply access the unique_id attribute
        for access to the machine's identifier
        """
        # use subprocess to check the wmic command output, and get the uuid
        wmic_id:str = subprocess.check_output('wmic csproduct get uuid')
        wmic_id = wmic_id.decode().split('\n')[1].strip()
        # use uuid.getnode() to get another unique pc identifier, which we
        # can then combine into an even safer pc id
        uuid_id:str = str(uuid.getnode())
        # combine the previous two ids into one larger, safer id
        self.unique_id = wmic_id + uuid_id
        self.unique_id = self.unique_id.replace('-','')
        self.unique_id = self.unique_id.replace('_','')
    
    def __repr__(self):
        # just so print() works for class instances
        return f'uniquePCIdentifier<{self.unique_id}>'

def getUniquePCIdentifier():
    return uniquePCIdentifier().unique_id

def getUniqueSymmetricKey():
    unique_identifier = getUniquePCIdentifier()
    return crypto.Symmetric.createKey(unique_identifier.encode())