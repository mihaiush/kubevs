#!/bin/bash -x

if grep __DEVMODE__ /etc/kubevs/config.yaml ; then
    cd /tmp
    if [ -n "$PROXY" ] ; then
        CURL_PROXY="https_proxy=${PROXY}"
    else
        CURL_PROXY=""
    fi
    $CURL_PROXY git clone https://github.com/mihaiush/kubevs.git
    cd kubevs
    git checkout dev
    cd app
else
    cd /opt/kubevs
fi

exec /usr/bin/python3 $1
