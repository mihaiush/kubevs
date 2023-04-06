#!/bin/bash

cd $(dirname $0)/..
TAG=$(git rev-list --count HEAD)-$(git rev-parse --short HEAD)
docker build -t mihaiush/kubevs:$TAG -f docker/Dockerfile .
