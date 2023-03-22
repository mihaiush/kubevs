#!/usr/bin/python3

from lib.kubewatch import KubeWatchController
from lib.common import *
import kubernetes
import traceback
import os
import yaml
import sys

LB_PREFIX = 'worker'

if CONFIG['controller']['debug']:
    LOG.enable_debug()

if CONFIG['worker']['type'] not in ['service']:
    LOG.error('Unknown type ()'.format(CONFIG['worker']['type']))
    sys.exit(2)

LOG.debug("Worker type '{}'".format(CONFIG['worker']['type']))

TPL = open('{}/lib/worker_tpl.yaml'.format(os.path.dirname(os.path.realpath(__file__))), 'r').read()
TPL = TPL.replace('{{TYPE}}', CONFIG['worker']['type'])
TPL = TPL.replace('{{IMAGE}}', os.environ['LB_IMAGE'])
TPL = TPL.replace('{{VERSION}}', os.environ['LB_IMAGE'].split(':')[-1])
def tpl2data(ns , n):
    d = TPL
    d = d.replace('{{NAMESPACE}}', ns)
    d = d.replace('{{SELECTOR}}', n)
    d = yaml.safe_load(d)
    return d

kubernetes.config.load_incluster_config()

kw = KubeWatchController(90)

first_run = True
while True:
    data = kw.get()
    if 'error' in data:
        LOG.error(data['error'])
    else:
        LOG.debug('[config-data] {}'.format(data))
        for lb in data['actual']:
            lb_name = '{}-{}-{}'.format(LB_PREFIX, lb['namespace'], lb['name'])
            # delete extra workers
            if not lb in data['config']:
                LOG.info('Delete deployment {}'.format(lb_name))
                try:
                    v1 = kubernetes.client.AppsV1Api()
                    v1.delete_namespaced_deployment(lb_name, 'lb')
                except:
                    LOG.error('\n{}'.format(traceback.format_exc()))
            # update existing workers
            if first_run:
                first_run = False
                LOG.info('Patch deployment {}'.format(lb_name))
                d = tpl2data(lb['namespace'], lb['name'])
                try:
                    v1 = kubernetes.client.AppsV1Api()
                    v1.patch_namespaced_deployment(lb_name, 'lb', d)
                except:
                    LOG.error('\n{}'.format(traceback.format_exc()))
        # create missing workers
        for cfg in data['config']:
            if not cfg in data['actual']:
                lb_name = '{}-{}-{}'.format(LB_PREFIX, cfg['namespace'], cfg['name'])
                LOG.info('Create deployment {}'.format(lb_name))
                d = tpl2data(cfg['namespace'], cfg['name'])
                try:
                    v1 = kubernetes.client.AppsV1Api()
                    v1.create_namespaced_deployment('lb', d)
                except:
                    LOG.error('\n{}'.format(traceback.format_exc()))
                