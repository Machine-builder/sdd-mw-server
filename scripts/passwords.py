from .hashing import hash_str

def get_password_hash(password) -> str:
    '''hashes a password'''
    return hash_str(password)

def compare_passwords(hash, password) -> bool:
    '''takes a hash and a password and checks
    if they match'''
    hashed_password = hash_str(password)
    return hash == hashed_password