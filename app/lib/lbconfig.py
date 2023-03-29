from .common import *
import threading
import re
from .helper_client import Helper

class LbConfig:

    def __init__(self, if_svc, delay=0):
        self.delay = delay # how many seconds of silence (no config event) to wait before applying the config
        self.if_svc = if_svc # service interfaces (svcX) list
        self.services = [] # ipvs services, KubeWatch format
        self.config_services = False
        self.ipvs_svc = None # ipvs services, ipvsadm format, from __apply_ipvs_svc()
        self.pods = [] # pods behind ipvs services
        self.config_pods = False
        self.pods_cache = {} # cache for actual pod configuration

 
        self.apply_timer = None
        self.enabled = True
        
        self.re_ip = re.compile(r' inet ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/32 ')
        self.re_svc = re.compile(r'^-A (-[tu]) ([^ ]+) -s ([^ ]+)( -p ([0-9]+))?')
        self.re_rip = re.compile(r'^-a (-[tu] [^ ]+) -r ([^ :]+):')

        self.event = threading.Event()
        self.event.set()

        self.helper = Helper(CONFIG['helper']['port'])


    def load(self, config):
        if 'pods' in config:
            self.pods = config['pods']
            self.config_pods = True
        
        if 'services' in config:
            self.services = config['services']
            self.config_services = True

        if self.delay:
            if self.apply_timer:
                self.apply_timer.cancel()
            self.apply_timer = threading.Timer(self.delay, self.__apply)
            self.apply_timer.start()
        else:
            self.__apply()


    def wait(self):
        self.event.wait()

    
    def __apply(self):
        try:
            self.event.clear() # engage lock - calling LbConfig.wait() blocks
            if self.enabled :
                LOG.debug('[LbConfig.apply] services:{}'.format(self.services))
                if self.config_services:
                    self.__apply_vip()
                    self.__apply_ipvs_svc()
                    self.config_services = False
                LOG.debug('[LbConfig.apply] pods:{}'.format(self.pods))
                if self.config_pods:
                    self.__apply_pod()
                    self.__apply_ipvs_rip()
                    self.config_pods = False
        finally:
            self.event.set()


    def __apply_vip(self):
        # prepare config ip list
        ip_config = []
        for svc in self.services:
            if not svc['ip'] in ip_config:
                ip_config.append(svc['ip'])
        LOG.debug('[LbConfig.apply-vip] config ip {}'.format(ip_config))
        # prepare actual ip list
        ip_actual = []
        out, rc = run('ip address show dev tunl0')
        for l in out.split('\n'):
            r = self.re_ip.search(l)
            if r != None:
                ip_actual.append(r.group(1))
        LOG.debug('[LbConfig.apply-vip] actual ip {}'.format(ip_actual))
        # do sync
        # delete extra ips from actual
        for ip in ip_actual:
            if ip not in ip_config:
                LOG.info('[LbConfig.apply-vip] delete {}'.format(ip))
                out, rc = run('ip address del {}/32 dev tunl0'.format(ip))
        # add missing ips in actual
        for ip in ip_config:
            if ip not in ip_actual:
                LOG.info('[LbConfig.apply-vip] add {}'.format(ip))
                out, rc = run('ip address add {}/32 dev tunl0'.format(ip))
                arp_update(ip, self.if_svc)


    def __apply_ipvs_svc(self):
        # prepare config service list
        svc_config = dict() 
        for svc in self.services:
            proto = svc['protocol'][0].lower()
            ip = svc['ip']
            port = svc['port']
            sched = svc['scheduler'].lower()
            persist = svc['persistent']
            if persist != None:
                persist = ' -p {}'.format(persist)
            else:
                persist = ''
            svc_config['-{} {}:{}'.format(proto, ip, port)] = '-s {}{}'.format(sched, persist)
        LOG.debug('[LbConfig.apply-ipvs-svc] config services {}'.format(svc_config))
        # prepare actual service list
        svc_actual = dict()
        out, rc = run('ipvsadm -Sn')
        for l in out.split('\n'):
            r = self.re_svc.search(l)
            if r != None:
                proto = r.group(1)
                ip_port = r.group(2)
                sched = r.group(3)
                persist = r.group(5)
                if persist != None:
                    persist = ' -p {}'.format(persist)
                else:
                    persist = ''
                svc_actual['{} {}'.format(proto, ip_port)] = '-s {}{}'.format(sched, persist)
        LOG.debug('[LbConfig.apply-ipvs-svc] actual services {}'.format(svc_actual))
        # delete extra services from actual
        for svc in svc_actual.keys():
            #LOG.debug('[LbConfig.apply-ipvs-svc] check to delete "{}"'.format(svc))
            if not svc in svc_config:
                LOG.info('[LbConfig.apply-ipvs-svc] delete "{}"'.format(svc))
                out, rc = run('ipvsadm -D {}'.format(svc))
        # add/edit config services
        for svc, param in svc_config.items():
            #LOG.debug('[LbConfig.apply-ipvs-svc] check to edit "{}" "{}"'.format(svc, param))
            if not svc in svc_actual:
                LOG.info('[LbConfig.apply-ipvs-svc] add "{}"'.format(svc))
                out, rc = run('ipvsadm -A {} {}'.format(svc, param))
            else:
                if param != svc_actual[svc]:
                    LOG.info('[LbConfig.apply-ipvs-svc] edit "{}", "{}" -> "{}"'.format(svc, svc_actual[svc], param))
                    out, rc = run('ipvsadm -E {} {}'.format(svc, param))
        self.ipvs_svc = svc_config.keys()


    def __apply_pod(self):
        ip_config = []
        for svc in self.services:
            ip = svc['ip']
            if not ip in ip_config:
                ip_config.append(ip)
        ip_config.sort()
        LOG.debug('[LbConfig.apply-pod] ip config {}'.format(ip_config))
        # prepare ready pod list
        pods_ready = {}
        for pod in self.pods:
            pods_ready['/'.join((pod['ns'], pod['name'], pod['ip']))] = pod
        LOG.debug('[LbConfig.apply-pod] ready pods {}'.format(pods_ready))
        #LOG.debug('[LbConfig.apply-pod] pod_cache before sync {}'.format(self.pods_cache))
        # cleanup cache
        to_del = []
        for pod in self.pods_cache.keys():
            if not pod in pods_ready:
                to_del.append(pod)
        for pod in to_del:
            LOG.debug('[LbConfig.apply-pod] delete from cache {}'.format(pod))
            del(self.pods_cache[pod])
        for pod, params in pods_ready.items():
            if pod not in self.pods_cache or self.pods_cache[pod] != ip_config:
                LOG.debug('[LbConfig.apply-pod] configure pod {}'.format(pod))
                if self.helper.tun(params['node'], params['ns'], params['name'], ip_config):
                    self.pods_cache[pod] = ip_config
            else:
                LOG.debug('[LbConfig.apply-pod] pod {} in cache'.format(pod))
        #LOG.debug('[LbConfig.apply-pod] pod_cache after sync {}'.format(self.pods_cache))


    def __apply_ipvs_rip(self):
        rip_config = []
        for pod in self.pods:
            rip_config.append(pod['ip'])
        LOG.debug('[LbConfig.apply-ipvs-rip] config rip {}'.format(rip_config))
        rip_actual = {}
        out, rc = run('ipvsadm -Sn')
        for l in out.split('\n'):
            r = self.re_rip.search(l)
            if r != None:
                svc = r.group(1)
                rip = r.group(2)
                if not svc in rip_actual:
                    rip_actual[svc] = []
                rip_actual[svc].append(rip)
        LOG.debug('[LbConfig.apply-ipvs-rip] actual rip {}'.format(rip_actual))
        # cleanup
        for svc, rip in rip_actual.items():
            for r in rip:
                if not r in rip_config:
                    LOG.info('[LbConfig.apply-ipvs-rip] delete rip {} from "{}"'.format(r, svc))
                    out, rc = run('ipvsadm -d {} -r {}'.format(svc,r))
        # sync
        for svc in self.ipvs_svc:
            for r in rip_config:
                if not svc in rip_actual or not r in rip_actual[svc]:
                    LOG.info('[LbConfig.apply-ipvs-rip] add rip {} to "{}"'.format(r, svc))
                    out, rc = run('ipvsadm -a {} -r {} -i'.format(svc,r))     


    def cleanup(self):
        self.enabled = False
        #LOG.debug('[LbConfig.cleanup] cleanup ipvs')
        #run('ipvsadm -C')
        for pod in self.pods:
            LOG.debug('[LbConfig.cleanup] cleanup pod {}/{}'.format(pod['ns'], pod['name']))
            self.helper.tun(pod['node'], pod['ns'], pod['name'], [0,])


        
