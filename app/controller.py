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

TPL = open('{}/lib/worker_tpl.yaml'.format(os.path.dirname(os.path.realpath(__file__))), 'r').read()
TPL = TPL.replace('{{PROXY}}', os.environ['PROXY'])
TPL = TPL.replace('{{IMAGE}}', os.environ['LB_IMAGE'])
TPL = TPL.replace('{{VERSION}}', os.environ['LB_IMAGE'].split(':')[-1])
def tpl2data(ns, n, i):
    d = TPL
    d = d.replace('{{NAMESPACE}}', ns)
    d = d.replace('{{SERVICE}}', n)
    d = d.replace('{{UID}}', i)
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
            #lb_name = '{}-{}-{}'.format(LB_PREFIX, lb['namespace'], lb['name'])
            lb_name = '{}-{}'.format(LB_PREFIX, lb['uid'])
            # delete extra workers
            if not lb in data['config']:
                LOG.info('Delete worker {}'.format(lb_name))
                try:
                    v1 = kubernetes.client.AppsV1Api()
                    v1.delete_namespaced_stateful_set(lb_name, 'kubevs')
                except:
                    LOG.error('\n{}'.format(traceback.format_exc()))
            # update existing workers
            if first_run:
                first_run = False
                LOG.info('Patch worker {}'.format(lb_name))
                d = tpl2data(lb['namespace'], lb['name'], lb['uid'])
                try:
                    v1 = kubernetes.client.AppsV1Api()
                    v1.patch_namespaced_stateful_set(lb_name, 'kubevs', d)
                except:
                    LOG.error('\n{}'.format(traceback.format_exc()))
        # create missing workers
        for cfg in data['config']:
            if not cfg in data['actual']:
                #lb_name = '{}-{}-{}'.format(LB_PREFIX, cfg['namespace'], cfg['name'])
                lb_name = '{}-{}'.format(LB_PREFIX, cfg['uid'])
                LOG.info('Create worker {}'.format(lb_name))
                d = tpl2data(cfg['namespace'], cfg['name'], cfg['uid'])
                try:
                    v1 = kubernetes.client.AppsV1Api()
                    v1.create_namespaced_stateful_set('kubevs', d)
                except:
                    LOG.error('\n{}'.format(traceback.format_exc()))
                
