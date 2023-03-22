import requests
from socket import getfqdn
from .common import CONFIG

class Helper:
    
    def __init__(self, port, config=CONFIG['helper']['authDir']):
        self.port = port
        cert = '{}/{}'.format(config, 'cert')
        token = open('{}/{}'.format(config, 'token'), 'r').read().split('\n')[0].strip()
        self.options = {
            'verify': cert,
            'headers': {'X-Token': token}
        }


    def svc(self, node, ns, pod):
        node = getfqdn(node)

        r = requests.get('https://{}:{}/svc?ns={}&pod={}'.format(node, self.port, ns, pod), **self.options)
        if r.status_code == 200:
            return r.text.split('\n')[0].strip().split(' ')
        else:
            r.raise_for_status()


    def tun(self, node, ns, pod, ip_list):
        node = getfqdn(node)

        ip_qs = ''
        for ip in ip_list:
            ip_qs = '{}&ip={}'.format(ip_qs, ip)

        r = requests.get('https://{}:{}/tun?ns={}&pod={}{}'.format(node, self.port, ns, pod, ip_qs), **self.options)
        if r.status_code == 200:
            return True
        else:
            return False
        
