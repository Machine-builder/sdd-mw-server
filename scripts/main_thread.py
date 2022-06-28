from http import client
import time, traceback
import logging

from PySide2.QtCore import QObject, Slot

class BackendFake():
    view:None
    app_ref:None
    handler:None
    executeJs:None
    client:None

class Worker:
    def __init__(self, callback_queue):
        self.backend = BackendFake()
        self.callback_queue = callback_queue
    
    def sendCallback(self, callback):
        self.callback_queue.put(callback)
    
    def run(self):
        self.client = self.backend.client
        while 1:
            events, connected = self.client.eb_client.pump()
            for event in events:
                self.sendCallback( (self.backend.processServerEvent, [event]) )