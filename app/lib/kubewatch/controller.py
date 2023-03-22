import kubernetes
from threading import Thread
from .basic import KubeWatchBasic
from time import sleep
from ..common import LOG, CONFIG

class KubeWatchController(KubeWatchBasic):

    def __init__(self, check=0):
        KubeWatchBasic.__init__(self, {'config':[], 'actual':[]}, check)       
 
        worker_svc = Thread(target=self.__watch_svc, daemon=True)
        worker_svc.start()

        worker_lb = Thread(target=self.__watch_lb, daemon=True)
        worker_lb.start()


    def __parse_svc(self, op, src):
        r = False
        data = {
            'namespace': src.metadata.namespace,
            'name': src.metadata.name,
        }
        if op == '+':
            if 'load_balancer_class' in src.spec and src.spec.load_balancer_class == 'kubevs':
                if not data in self.data['config']:
                    self.data['config'].append(data)
                    r = True
            else:
                if data in self.data['config']:
                    self.data['config'].remove(data)
                    r = True
        else:
            if data in self.data['config']:
                self.data['config'].remove(data)
                r = True
        return r


    def __parse_lb(self, op, src):
        r = False
        data = {
            'namespace': src['lb_namespace'],
            'name': src['lb_selector'],
        }
        if op == '+':
            if not data in self.data['actual']:
                self.data['actual'].append(data)
                r = True
        else:
            if data in self.data['actual']:
                self.data['actual'].remove(data)
                r = True
        return r


    def full(self):
        try:
            v1 = kubernetes.client.CoreV1Api()
            for i in v1.list_service_for_all_namespaces().items:
                self.__parse_svc('+', i)
        except:
            self.error("Can't list services")
        try:
            v1 = kubernetes.client.AppsV1Api()
            for i in v1.list_namespaced_deployment('lb', label_selector='app=kubevs-worker').items:
                self.__parse_lb('+', i.metadata.labels)
        except:
            self.error("Can't list workers")


    def __watch_svc(self):
        while True:
            exp = False
            try:
                v1 = kubernetes.client.CoreV1Api()
                w = kubernetes.watch.Watch()
                for e in w.stream(v1.list_service_for_all_namespaces):
                    if e['type'] == 'ERROR' and e['raw_object']['reason'] == 'Expired':
                        exp = True
                    else:
                        if e['type'] == 'DELETED':
                            t = '-'
                        else:
                            t = '+'
                        if self.__parse_svc(t, e['object']):
                            self.put()
            except:
                if exp:
                    LOG.debug('[KubeWatchLbSvc.watch-svc] expire')                    
                else:
                    self.error("Can't watch services")
                    sleep(2)


    def __watch_lb(self):
        while True:
            exp = False
            try:
                v1 = kubernetes.client.AppsV1Api()
                w = kubernetes.watch.Watch()
                for e in w.stream(v1.list_namespaced_deployment, 'lb', label_selector='app=kubevs-worker'):
                    if e['type'] == 'ERROR' and e['raw_object']['reason'] == 'Expired':
                        exp = True
                    else:
                        if e['type'] == 'DELETED':
                            t = '-'
                        else:
                            t = '+'
                        if self.__parse_lb(t, e['object'].metadata.labels):
                            self.put()
            except:
                if exp:
                    LOG.debug('[KubeWatchLbSvc.watch-lb] expire')         
                else:
                    self.error("Can't watch lbs")
                    sleep(2)



