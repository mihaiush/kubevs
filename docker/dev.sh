#!/bin/bash -x

cd /tmp

https_proxy=http://popp-proxy-qa-bs01.po.server.lan:3128/ git clone https://github.com/mihaiush/kubevs.git
cd kubevs
git checkout dev

/usr/bin/python3 $1
