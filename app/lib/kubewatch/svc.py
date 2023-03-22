import kubernetes
from threading import Thread
import yaml
from .basic import KubeWatchBasic
from time import sleep
from ..common import LOG

class KubeWatchSvc(KubeWatchBasic):

    def __init__(self, ns, svc, check=0):
        self.ns = ns
        self.svc = svc

        KubeWatchBasic.__init__(self, {'services': [], 'pods': []}, check)
        
        worker_svc = Thread(target=self.__watch_svc, daemon=True)
        worker_svc.start()

        worker_ep = Thread(target=self.__watch_ep, daemon=True)
        worker_ep.start()

    def full(self):
        try:
            v1 = kubernetes.client.CoreV1Api()
            r = v1.read_namespaced_service(self.svc, self.ns)
            self.__parse_svc(r.metadata.annotations)
        except:
            self.error("Can't read service")
        try:
            v1 = kubernetes.client.CoreV1Api()
            r = v1.read_namespaced_endpoints(self.svc, self.ns)
            self.__parse_ep(r.subsets[0].addresses)
        except:
            self.error("Can't read endpoints")
        #LOG.debug('[KubeWatchSvc.full] data-out: {}'.format(self.data))

    def __parse_svc(self, src):
        if 'lb/config' in src:
            data = src['lb/config']
            try:
                data = yaml.safe_load(data)
                data = data['services']
                
                # service defaults:
                # - protocol tcp
                # - shceduler rr
                # - persistence None 
                for k in range(len(data)):
                    if not 'protocol' in data[k]:
                        data[k]['protocol'] = 'tcp'
                    if not 'scheduler' in data[k]:
                        data[k]['scheduler'] = 'rr'
                    if not 'persistence' in data[k]:
                        data[k]['persistence'] = None

                if data != self.data['services']:
                    self.data['services'] = data
                    return True
            except:
                self.error("Can't load 'lb/config' annotation")
            return False

    def __parse_ep(self, src):
        data = list()
        for a in src:
            data.append({
                'ip': a.ip,
                'node': a.node_name,
                'name': a.target_ref.name,
                'ns': a.target_ref.namespace,
            })
        if data != self.data['pods']:
            self.data['pods'] = data
            return True
        return False
        
    def __watch_svc(self):
        while True:
            exp = False
            try:
                v1 = kubernetes.client.CoreV1Api()
                w = kubernetes.watch.Watch()
                for e in w.stream(v1.list_namespaced_service, self.ns, field_selector='metadata.name={}'.format(self.svc)):
                    #LOG.debug('[KubeWatchSvc.watch-svc] data-in: {}'.format(self.data))
                    if e['type'] == 'ERROR' and e['raw_object']['reason'] == 'Expired':
                        exp = True
                    elif self.__parse_svc(e['object'].metadata.annotations):
                        self.put()
            except:
                if exp:
                    LOG.debug('[KubeWatchSvc.watch-svc] expire')
                else:
                    self.error("Can't watch service\n{}".format(e))
                    sleep(2)

    def __watch_ep(self):
        while True:
            exp = False
            try:
                v1 = kubernetes.client.CoreV1Api()
                w = kubernetes.watch.Watch()
                for e in w.stream(v1.list_namespaced_endpoints, self.ns, field_selector='metadata.name={}'.format(self.svc)):
                    if e['type'] == 'ERROR' and e['raw_object']['reason'] == 'Expired':
                        exp = True
                    #LOG.debug('[KubeWatchSvc.watch-ep] data-in: {}'.format(self.data))
                    elif self.__parse_ep(e['object'].subsets[0].addresses):
                        self.put()
            except:
                if exp:
                    LOG.debug('[KubeWatchSvc.watch-ep] expire')
                else:
                    self.error("Can't watch endpoints\n{}".format(e))
                    sleep(2)


