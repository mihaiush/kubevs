import kubernetes
from threading import Thread
from queue import SimpleQueue
from time import sleep
import traceback
from ..common import LOG

kubernetes.config.load_incluster_config()

class KubeWatchBasic:

    def __init__(self, data_template, check=0):
        self.data = data_template
        self.check = check
        self.q = SimpleQueue()

        self.__full()

        if check:
            worker_timer = Thread(target=self.__timer, daemon=True)
            worker_timer.start() 

    def __timer(self):
        while True:
            sleep(self.check)
            self.__full()

    def put(self):
        return self.q.put(self.data)

    def get(self):
        return self.q.get()

    def error(self, msg):
        self.q.put({'error': '{}:\n{}'.format(msg, traceback.format_exc())})

    def __full(self):
        self.full()
        self.put()

    def full(self):
        raise NotImplementedError


