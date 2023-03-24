import subprocess
import logging
import shlex
import sys
import time
import yaml

class Logger(logging.Logger):
    def __init__(self, name):
        logging.Logger.__init__(self, name)
        self.setLevel(logging.INFO)
        lh = logging.StreamHandler(sys.stderr)
        lh.setFormatter(logging.Formatter('%(asctime)-15s %(levelname)s %(message)s'))
        self.addHandler(lh)

    def enable_debug(self):
        self.setLevel(logging.DEBUG)

logging.setLoggerClass(Logger)
LOG = logging.getLogger('lb')

def b2str(s) :
    return s.decode('ascii').strip()

def run(cmd, log_error=True):
    try:
        p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, err = p.communicate()
        out = b2str(out)
        rc = p.returncode
        msg = '[run] {}\n{}\n{}'.format(cmd, out, rc)
    except Exception as e:
        rc = -1
        msg = '[run] {}\n{}\n{}'.format(cmd, e, rc)
    if rc == 0 or (rc > 0 and not log_error):
        LOG.debug(msg)
    elif rc < 0 or (rc > 0 and log_error):
        LOG.error(msg)
    return out, rc

def check_rc(cmd):
    out, rc = run(cmd)
    if rc != 0:
        sys.exit(1)
    return out, rc

def arp_update(ip, interfaces):
    for x in range(2):
        for iface in interfaces:
            out, rc = run('arping -U -c1 -I {} {}'.format(iface, ip))
        time.sleep(0.1)

CONFIG = yaml.safe_load(open('/etc/kubevs/config.yaml', 'r').read())
CONFIG['helper']['authDir'] = '/etc/kubevs/helper-auth'
