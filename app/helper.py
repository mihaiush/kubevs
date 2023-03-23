from lib.common import *
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
#from io import BytesIO
from urllib.parse import parse_qs
from base64 import b64encode
import re
import hashlib
import os
import json
import ssl

TOKEN = open('{}/token'.format(CONFIG['helper']['authDir']), 'r').read().split('\n')[0].strip()

if CONFIG['helper']['debug']:
    LOG.enable_debug()

def get_netns(pns, pname):
    pod = '{}/{}'.format(pns,pname)
    err = False
    # Get cri pod_id
    out, rc = run("crictl pods -o json --namespace {} --name {}".format(pns, pname))
    if rc != 0:
        err = True
    else:
        out = json.loads(out)['items']
        if len(out) < 1:
            LOG.error('[get-netns] pod={} not found'.format(pod))
            out = 'pod not found'
            err = True
        else:
            i = out[0]['id']
            LOG.debug('[get-netns] pod={}, pod_id={}'.format(pod, i))
            # Get container_id
            out, rc = run('crictl ps -p {} -o json'.format(i))
            i = json.loads(out)['containers'][0]['id']
            LOG.debug('[get-netns] pod={}, container_id={}'.format(pod, i))
            # Get container pid
            out, rc = run('crictl inspect -o json {}'.format(i))
            pid = json.loads(out)['info']['pid']
            LOG.debug('[get-netns] pod={}, pid={}'.format(pod, pid))
            out = '/proc/{}/ns/net'.format(pid)
            LOG.debug('[get-netns] pod={}, netns={}'.format(pod, out))
    return out, err

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class RequestHandler(BaseHTTPRequestHandler):

    response_text = 'OK'
    response_code = 200
    re_ip = re.compile(r' inet ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/32')
    re_if = re.compile(r'^[0-9]+: ([^ @:]+)[@:]')

    def response(self, text, code=200):
        self.response_text = text
        self.response_code = code

    def syntax_error(self):
        response = 'BAD-SYNTAX\n'
        response = response + 'Configure service interfaces on lb pods - /svc?ns=NAMESPACE&pod=POD-NAME\n'
        response = response + 'Configure tun interfaces on client pods - /tun?ns=NAMESPACE&pod=POD-NAME&ip=IP1&ip=IP2...\n'
        self.response(response, 400)

    def server_error(self, e):
        self.response('ERROR\n{}'.format(e), 500)

    def do_svc(self, pns, pname):
        pod = '{}/{}'.format(pns,pname)
        ns, err = get_netns(pns, pname)
        if err:
            self.server_error(ns)
            return
        LOG.debug('[svc] pod={}'.format(pod))
        # Check client ip address
        #out, rc = run('nsenter --net={} ip address show dev eth0'.format(ns))
        out, rc = run('nsenter --net={} hostname --all-ip-addresses'.format(ns))
        if not self.client_address[0] in out:
            LOG.error("[svc] pod={}, client ip address doesn't match pod ip address".format(pod))
            self.response('FORBIDDEN', 403)
            return
        # Make svc interfaces
        k = re.sub('[\+\/=]', '', b64encode(hashlib.md5(ns.encode()).digest()).decode('ascii'))[0:8]
        response = []
        for j,i in enumerate(CONFIG['helper']['if']):
            svc_pod = 'svc{}'.format(j)
            svc_host = '{}{}'.format(svc_pod, k)
            # Check pod interfaces
            out, rc = run('nsenter --net={} ip link show {}'.format(ns, svc_pod), log_error=False)
            if rc > 0:
                # No pod interface, create host interface
                LOG.debug('[svc] pod={}, create host interface {}'.format(pod, svc_host))
                out, rc = run('ip link add {} link {} type macvlan mode bridge'.format(svc_host, i))
                if rc != 0:
                    self.server_error(out)
                    return
                # Move host interface in pod
                LOG.debug('[svc] pod={}, move host interface {} in netns {}'.format(pod, svc_host, ns))
                out, rc = run('ip link set {} netns {}'.format(svc_host, ns))
                if rc != 0:
                    self.server_error(out)
                    return
                # Rename pod interface
                LOG.info('[svc] pod={}, create interface {}'.format(pod, svc_pod))
                out, rc = run('nsenter --net={} ip link set {} name {}'.format(ns, svc_host, svc_pod))
                if rc != 0:
                    self.server_error(out)
                    return
            elif rc < 0:
                self.server_error(out)
                return
            else:
                LOG.debug('[svc] pod={}, interface {} already exists'.format(pod, svc_pod))
            response.append(svc_pod)
        self.response(' '.join(response))

    def do_tun(self, pns, pname, ip_config):
        pod = '{}/{}'.format(pns,pname)
        ns, err = get_netns(pns, pname)
        if err:
            self.server_error(ns)
            return
        LOG.debug('[tun] pod={}, ip_config={}'.format(pod, ip_config))
        # check sysctl
        out, rc = run('nsenter --net={} sysctl -n net.ipv4.conf.tunl0.rp_filter'.format(ns))
        if out.split('\n')[0] != '2':
            LOG.debug('[tun] pod={} netns config'.format(pod))
            run('nsenter --net={} ip link set tunl0 up'.format(ns))
            run('nsenter --net={} sysctl net.ipv4.tcp_keepalive_time=600'.format(ns))
            run('nsenter --net={} sysctl net.ipv4.ip_forward=1'.format(ns))
            run('nsenter --net={} sysctl net.ipv4.conf.all.arp_ignore=1'.format(ns))
            run('nsenter --net={} sysctl net.ipv4.conf.all.arp_announce=2'.format(ns))
            # apparenly not necessary, actual arp seting max(all, if), http://kb.linuxvirtualserver.org/wiki/Using_arp_announce/arp_ignore_to_disable_ARP
            #out, rc = run('nsenter --net={} ip link show'.format(ns))
            #for l in out.split('\n'):
            #    r = self.re_if.search(l)
            #    if r != None:
            #        run('nsenter --net={} sysctl net.ipv4.conf.{}.arp_ignore=1'.format(ns, r.group(1)))
            #        run('nsenter --net={} sysctl net.ipv4.conf.{}.arp_announce=2'.format(ns, r.group(1)))
            run('nsenter --net={} sysctl net.ipv4.conf.tunl0.rp_filter=2'.format(ns))
        else:
            LOG.debug('[tun] pod={} netns OK'.format(pod))
        ip_actual = []
        out, rc = run('nsenter --net={} ip addr show dev tunl0'.format(ns))
        for l in out.split('\n'):
                r = self.re_ip.search(l)
                if r != None:
                    ip_actual.append(r.group(1))
        LOG.debug('[tun] pod={}, ip_actual={}'.format(pod, ip_actual))
        if ip_config[0] != '0':
            # sync
            # cleanup actual
            err = None
            for ip in ip_actual:
                if ip not in ip_config:
                    LOG.info('[tun] pod={} delete {}@tunl0'.format(pod, ip))
                    out, rc = run('nsenter --net={} ip addr del {}/32 dev tunl0'.format(ns, ip))
                    if rc != 0:
                        err = out
                        break
            if err != None:
                self.response(err, 500)
            # add missing ips
            err = None
            for ip in ip_config:
                if ip not in ip_actual:
                    LOG.info('[tun] pod={} add {}@tunl0'.format(pod, ip))
                    out, rc = run('nsenter --net={} ip addr add {}/32 dev tunl0'.format(ns, ip))
                    if rc != 0:
                        err = out
                        break
        else:
            # cleanup
            err = None
            for ip in ip_actual:
                LOG.info('[tun] pod={} cleanup {}@tunl0'.format(pod, ip))
                out, rc = run('nsenter --net={} ip addr del {}/32 dev tunl0'.format(ns, ip))
                if rc != 0:
                    err = out
                    break
        if err != None:
            self.response(err, 500)
        self.response('OK')

    def do_GET(self):
        xt = self.headers.get('X-Token')
        if xt != TOKEN:
            LOG.error("X-Token ({}) doesn't match config token ({})".format(xt, TOKEN))
            self.response('FORBIDDEN', 403)
        else:
            request = self.path.split('?')
            command = request[0]
            # Check if there are parameters
            if len(request)>1:
                parameters = parse_qs(request[1])
                # 'ns' and 'pod' parameter are mandatory for all commands
                if not 'ns' or not 'pod' in parameters:
                    self.syntax_error()
                else:
                    pns = parameters['ns'][0]
                    pname = parameters['pod'][0]
                    # 'svc' command
                    if command == '/svc':
                        self.do_svc(pns, pname)
                    # 'tun' command, 'ip' parameter is mandatory
                    elif command == '/tun' and 'ip' in parameters:
                        self.do_tun(pns, pname, parameters['ip'])
                    # wrong or no command
                    else:
                        self.syntax_error()
            else:
                self.syntax_error()
        self.send_response(self.response_code)
        self.end_headers()
        response = '{}\n'.format(self.response_text)
        self.wfile.write(response.encode('utf-8'))

# Check external commands
check_rc('ip -V')
check_rc('crictl -v')
check_rc('sysctl -V')
check_rc('nsenter -V')

# Check eth interface
for i in CONFIG['helper']['if']:
    out, rc = run('ip link show {} up'.format(i))
    if rc != 0:
        sys.exit(1)
    elif out == '':
        LOG.error('{} down'.format(i))
        sys.exit(1)


httpd = ThreadingHTTPServer(('0.0.0.0', CONFIG['helper']['port']), RequestHandler)
ssl_context = ssl.create_default_context()
ssl_context.load_cert_chain('{}/cert'.format(CONFIG['helper']['authDir']), '{}/key'.format(CONFIG['helper']['authDir']))
#httpd.socket = ssl.wrap_socket (httpd.socket, keyfile='{}/key'.format(CONFIG['helper']['authDir']), certfile='{}/cert'.format(CONFIG['helper']['authDir']), server_side=True)
httpd.socket = ssl_context.wrap_socket (httpd.socket, server_side=True)

LOG.info('Starting helper on port {}'.format(CONFIG['helper']['port']))
httpd.serve_forever()
