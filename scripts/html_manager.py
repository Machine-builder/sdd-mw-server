import os
from PySide2 import QtCore

class Handler():
    def __init__(self, cd):
        # get the current directory
        self.current_dir = cd
        # get the directory where the html files are stored
        self.html_dir = os.path.join(self.current_dir, 'html/')
        self.view = None
        self.last_loaded_page = None

    def setView(self,view):
        self.view = view

    def html_page_path(self,fn):
        # get the filename of the html
        return os.path.join(self.html_dir, fn)

    def QUrl(self,fn):
        return QtCore.QUrl.fromLocalFile(self.html_page_path(fn))

    def load_page(self,fn):
        self.view.load(self.QUrl(fn))

    def load_html(self,htmlfn):
        filepath = self.html_page_path(htmlfn)
        self.last_loaded_page = htmlfn
        self.load_page(filepath)
        
    def load_url(self,url):
        self.view.load(QtCore.QUrl(url))