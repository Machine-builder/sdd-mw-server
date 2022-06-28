import hashlib

def hash_str(s):
    return hashlib.sha256(s.encode()).hexdigest()