#!/bin/bash -x

if grep __DEVMODE__ /etc/kubevs/config.yaml ; then
    cd /tmp
    https_proxy=http://popp-proxy-qa-bs01.po.server.lan:3128/ git clone https://github.com/mihaiush/kubevs.git
    cd kubevs
    git checkout dev
    cd app
else
    cd /opt/kubevs
fi

exec /usr/bin/python3 $1
