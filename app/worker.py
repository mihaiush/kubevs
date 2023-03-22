#!/usr/bin/python3

from os import environ
from lib.kubewatch import KubeWatchWorker
from lib.lbconfig import LbConfig
from lib.helper_client import Helper
from lib.common import *
import signal
from sys import exit

if CONFIG['worker']['debug']:
    LOG.enable_debug()

# Check external commands
check_rc('ip -V')
check_rc('sysctl -V')

check_rc('sysctl net.ipv4.ip_forward=1')
check_rc('sysctl net.ipv4.conf.all.arp_ignore=0')
check_rc('sysctl net.ipv4.conf.all.arp_announce=0')
check_rc('ip link set tunl0 up')

# Create svc interfaces
LOG.debug('create svc interfaces')
helper = Helper(CONFIG['helper']['port'])
if_svc = helper.svc(environ['KUBERNETES_NODE_NAME'], environ['KUBERNETES_NAMESPACE'], environ['KUBERNETES_POD_NAME'])
LOG.debug('svc interfaces {}'.format(if_svc))

# Up svc interfaces
for svc_if in if_svc:
    LOG.info('{} up'.format(svc_if))
    check_rc('sysctl net.ipv4.conf.{}.arp_ignore=0'.format(svc_if))
    check_rc('sysctl net.ipv4.conf.{}.arp_announce=0'.format(svc_if))
    check_rc('ip link set {} up'.format(svc_if))

# Watch for kubernetes changes
kw = KubeWatchWorker(environ['LB_NAMESPACE'], environ['LB_SELECTOR'], 90)

# VIP + IPVS configurator
cfg = LbConfig(if_svc, 0)

def cleanup(signum, frame):
    cfg.cleanup()
    exit()

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

while True:
    cfg.wait()
    data = kw.get()
    if 'error' in data:
        LOG.error(data['error'])
    else:
        LOG.debug('[config-data] {}'.format(data))
        cfg.load(data)

