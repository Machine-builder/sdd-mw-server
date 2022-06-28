from random import sample
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from scripts.constants import CONSTANTS

class Asymmetric:
    """
    Asymmetric encryption functions
    """
    # ------------------------- key generation
    @staticmethod
    def createKeyPair(public_exponent=65537, key_size=2048):
        """
        Generate a public and private
        key
        """
        private_key = rsa.generate_private_key(
            public_exponent=public_exponent,
            key_size=key_size,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        return public_key, private_key

    # ------------------------- keys to bytes / bytes to keys
    @staticmethod
    def keyToBytes(key, key_type:int=0):
        """
        Convert a key to bytes
        key_type = 0 for public key
        key_type = 1 for private key
        """
        pem = None
        if key_type == 0:
            pem = key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo)
        elif key_type == 1:
            pem = key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption())
        return pem
    
    @staticmethod
    def keyFromBytes(bytes, key_type:int=0):
        """
        Load a key from bytes
        key_type = 0 for public key
        key_type = 1 for private key
        """
        key = None
        if key_type == 0:
            key = serialization.load_pem_public_key(
                bytes,
                backend=default_backend())
        elif key_type == 1:
            key = serialization.load_pem_private_key(
                bytes,
                password=None,
                backend=default_backend())
        return key

    # ------------------------- store / load keys
    @staticmethod
    def storeKey(key, filename:str, key_type:int=0):
        """
        Store a key in a file
        key_type = 0 for public key
        key_type = 1 for private key
        """
        pem = Asymmetric.keyToBytes(key, key_type)
        with open(filename, 'wb') as f:
            f.write(pem)
    
    @staticmethod
    def loadKey(filename:str, key_type:int=0):
        """
        Load a key from a file
        key_type = 0 for public key
        key_type = 1 for private key
        """
        with open(filename, 'rb') as f:
            return Asymmetric.keyFromBytes(f.read(), key_type)

    # ------------------------- store / load key pairs
    @staticmethod    
    def storeKeyPair(public_key, private_key, filename_prefix:str):
        """
        Store public and private
        keys in files
        """
        Asymmetric.storeKey(public_key, f"{filename_prefix}_pub.k", 0)
        Asymmetric.storeKey(private_key, f"{filename_prefix}_pri.k", 1)
    
    @staticmethod
    def loadKeyPair(public_key, private_key, filename_prefix:str):
        """
        Load public and private
        keys from files
        """
        public_key = Asymmetric.loadKey(f"{filename_prefix}_pub.k", 0)
        private_key = Asymmetric.loadKey(f"{filename_prefix}_pri.k", 1)
        return public_key, private_key

    # ------------------------- encrypt / decrypt bytes
    @staticmethod
    def encryptBytes(bytes, public_key):
        """
        Encrypt bytes using key
        """
        return public_key.encrypt(
            bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None))
    
    @staticmethod
    def decryptBytes(bytes, private_key):
        """
        Decrypt bytes using key
        """
        return private_key.decrypt(
            bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None))

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class Symmetric:
    """
    Symmetric encryption functions
    """
    # ------------------------- key generation
    @staticmethod
    def createKey(password:bytes=None):
        """
        Generate a symmetric key, optionally
        using a provided password
        """
        # pw is arbitrary I guess
        pw = password or "69420".encode()
        salt = os.urandom(16)
        if password != None:
            salt = b'\x85\x94\xa2 \x9e\xc43\xa11\xdb\xbc\x1fH\xf6\x0e\xbc'
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000, backend=default_backend())
        sym_key = base64.urlsafe_b64encode(kdf.derive(pw))
        return sym_key
    
    # ------------------------- encrypt / decrypt bytes
    @staticmethod
    def encryptBytes(bytes, sym_key):
        """
        Encrypt bytes using a symmetric key
        """
        fernet = Fernet(sym_key)
        encrypted = fernet.encrypt(bytes)
        return encrypted
    
    @staticmethod
    def decryptBytes(bytes, sym_key):
        """
        Decrypt bytes using a symmetric key
        """
        fernet = Fernet(sym_key)
        decrypted = fernet.decrypt(bytes)
        return decrypted

class Hybrid:
    """
    Hybrid encryption functions
    (Combinations of symmetric and asymmetric)
    """
    # ------------------------- encrypt / decrypt bytes
    @staticmethod
    def encryptBytes(bytes, sym_key, public_key):
        """
        Encrypt bytes using a symmetric key,
        then encrypt symmetric key using public key
        (returns the encrypted bytes and encrypted key)
        """
        if sym_key is None:
            sym_key = Symmetric.createKey()
        bytes_encrypted = Symmetric.encryptBytes(bytes, sym_key)
        sym_key_encrypted = Asymmetric.encryptBytes(sym_key, public_key)
        return bytes_encrypted, sym_key_encrypted
    
    @staticmethod
    def decryptBytes(bytes, sym_key, private_key):
        """
        Encrypt bytes using a symmetric key,
        then encrypt symmetric key using public key
        (returns the decrypted bytes and decrypted key)
        """
        sym_key_decrypted = Asymmetric.decryptBytes(sym_key, private_key)
        bytes_decrypted = Symmetric.decryptBytes(bytes, sym_key_decrypted)
        return bytes_decrypted, sym_key_decrypted
    
class DataPacket(object):
    def __init__(self, payload, sym_key=None):
        self.payload = payload
        self.sym_key = sym_key
        self.encrypted = False
        if self.sym_key == None:
            self.sym_key = Symmetric.createKey()
    
    def encrypt(self, public_key, can_raise_error=False):
        """
        Encrypt this packet using a public key.
        *IN-PLACE*

        Function may raise AssertionError
        if the packet is already encrypted
        when called and can_raise_error is True
        """
        if can_raise_error:
            assert not self.encrypted, "packet is already encrypted"
        payload_encrypted, sym_key_encrypted = \
            Hybrid.encryptBytes(self.payload, self.sym_key, public_key)
        self.payload = payload_encrypted
        self.sym_key = sym_key_encrypted
        self.encrypted = True
    
    def decrypt(self, private_key, can_raise_error=False):
        """
        Decrypt this packet using a private key.
        *IN-PLACE*

        Function may raise AssertionError
        if the packet is already decrypted
        when called and can_raise_error is True
        """
        if can_raise_error:
            assert self.encrypted, "packet is already decrypted"
        payload, sym_key = \
            Hybrid.decryptBytes(self.payload, self.sym_key, private_key)
        self.payload = payload
        self.sym_key = sym_key
        self.encrypted = False               


def mainTest():

    class testUser(object):
        def __init__(self):
            pu, pr = Asymmetric.createKeyPair()
            self.key_pub = pu
            self.key_priv = pr
            self.info_received = {}
        
        def sendInfoTo(self, other, key, value):
            other.info_received[key] = value

    # test to simulate two users and
    # establish an end-to-end encrypted
    # communication channel between
    # them

    print()
    print("+++ E2E communication simulation +++")

    user_a = testUser()
    user_b = testUser()


    # ~~~ perspective: user_b ~~~

    key_pub_bytes = Asymmetric.keyToBytes(
        user_b.key_pub, CONSTANTS.PUBLIC)
    key_priv_bytes = Asymmetric.keyToBytes(
        user_b.key_priv, CONSTANTS.PRIVATE)

    assert type(key_pub_bytes) == bytes
    assert type(key_priv_bytes) == bytes

    user_b.sendInfoTo(user_a, "key_pub_bytes", key_pub_bytes)


    # ~~~ perspective: user_a ~~~

    # access the public key that user_b
    # previously sent over (in bytes form)
    key_pub_use_bytes = user_a.info_received["key_pub_bytes"]

    # load the key from bytes
    key_pub_use = Asymmetric.keyFromBytes(
        key_pub_use_bytes, CONSTANTS.PUBLIC)

    # convert own keys to bytes,
    # so they can be encrypted and sent
    key_pub_bytes = Asymmetric.keyToBytes(
        user_a.key_pub, CONSTANTS.PUBLIC)
    key_priv_bytes = Asymmetric.keyToBytes(
        user_a.key_priv, CONSTANTS.PRIVATE)
    
    # create packets to hold own key pair,
    # then encrypt the packets using user_b's public key
    packet_key_pub_bytes = DataPacket(key_pub_bytes)
    packet_key_priv_bytes = DataPacket(key_priv_bytes)
    packet_key_pub_bytes.encrypt(key_pub_use)
    packet_key_priv_bytes.encrypt(key_pub_use)

    user_a.sendInfoTo(user_b, "packet_key_shared_pub_enc", packet_key_pub_bytes)
    user_a.sendInfoTo(user_b, "packet_key_shared_priv_enc", packet_key_priv_bytes)


    # ~~~ perspective: user_b ~~~

    packet_key_pub = user_b.info_received["packet_key_shared_pub_enc"]
    packet_key_priv = user_b.info_received["packet_key_shared_priv_enc"]
    # decrypt the data packets
    packet_key_pub.decrypt(user_b.key_priv)
    packet_key_priv.decrypt(user_b.key_priv)
    # get the (now decrypted) payload from the packets
    key_shared_pub_bytes = packet_key_pub.payload
    key_shared_priv_bytes = packet_key_priv.payload
    # convert the bytes back into keys
    key_shared_pub = Asymmetric.keyFromBytes(key_shared_pub_bytes, CONSTANTS.PUBLIC)
    key_shared_priv = Asymmetric.keyFromBytes(key_shared_priv_bytes, CONSTANTS.PRIVATE)
    user_b.key_pub = key_shared_pub
    user_b.key_priv = key_shared_priv


    # test to ensure the keys transferred properly

    sample_data = b'worked flawlessly'

    # user user_b's key to decrypt something encrypted by user_a's key
    sample_data_encrypted = Asymmetric.encryptBytes(sample_data, user_a.key_pub)
    print(Asymmetric.decryptBytes(sample_data_encrypted, user_b.key_priv))

    # user user_a's key to decrypt something encrypted by user_b's key
    sample_data_encrypted = Asymmetric.encryptBytes(sample_data, user_b.key_pub)
    print(Asymmetric.decryptBytes(sample_data_encrypted, user_a.key_priv))



    sample_data = (
        'This is a test message!\n'
        'It will be encrypted safely, using a hybrid \n'
        'algorithm, which makes use of both symmetric \n'
        'and asymmetric encryption to encrypt a payload \n'
        'of theoretically any size!'
    ).encode()
    
    # hybrid encryption using symmetric and asymmetric keys

    print()
    print("+++ Encryption system using 2 key types +++")

    k_pub, k_priv = Asymmetric.createKeyPair()

    print()
    print(sample_data.decode())

    sample_data_encrypted, sym_key_encrypted = Hybrid.encryptBytes(
        sample_data,
        None,
        k_pub)
        
    print()
    print(sample_data_encrypted)

    sample_data_decrypted, sym_key_decrypted = Hybrid.decryptBytes(
        sample_data_encrypted,
        sym_key_encrypted,
        k_priv)

    print()
    print(sample_data_decrypted.decode())
    assert sample_data_decrypted == sample_data



    # hybrid encryption using only asymmetric keys
    # (symmetric keys used in black box)

    print()
    print("+++ Encryption system using packets +++")

    k_pub2, k_priv2 = Asymmetric.createKeyPair()
    packet = DataPacket(sample_data)

    print()
    print(packet.payload.decode())

    packet.encrypt(k_pub2)
    
    print()
    print(packet.payload.decode())

    packet.decrypt(k_priv2)

    print()
    print(packet.payload.decode())
    assert packet.payload == sample_data







if __name__ == '__main__':
    mainTest()