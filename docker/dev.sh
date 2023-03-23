#!/bin/bash

cd /tmp

git clone https://github.com/mihaiush/kubevs.git
cd kubevs
git checkout dev

/usr/bin/python3 $1
