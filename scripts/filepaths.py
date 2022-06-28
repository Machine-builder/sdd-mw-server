import os
import logging


class relativeFilepath(object):
    def __init__(self, parent_path: str):
        self.parent_path = parent_path

    def filepath(self, child_path: str):
        return os.path.join(self.parent_path, child_path)


def copyFIle(src: str, dest: str, overwrite: bool = True):
    """a full logging-based copy file function"""
    if not os.path.exists(src):
        logging.warning(
            f"cannot copy file, as src file does not exit -> {src}")
    try:        
        with open(src, 'rb') as file_r:
            raw = file_r.read()
    except Exception as e:
        logging.warning(
            f"error copying file at (r) -> {str(e)}")
        return
    if (not overwrite) and os.path.exists(dest):
        logging.warning(
            f"cannot copy file, as file already exists -> {src} -> {dest}")
        return
    try:    
        with open(dest, 'wb') as file_w:
            file_w.write(raw)
    except Exception as e:
        logging.warning(
            f"error copying file at (w) -> {str(e)}")
        return
    return True


def getDataPath():
    return os.path.join(os.getcwd(), 'resources/data/')