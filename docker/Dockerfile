FROM debian:testing-slim

USER 0

ADD docker/crictl.yaml /etc/

RUN DEBIAN_FRONTEND=noninteractive apt-get -q -y update
RUN DEBIAN_FRONTEND=noninteractive apt-get -q -y install ca-certificates apt-transport-https 

ADD docker/kubernetes.list /etc/apt/sources.list.d/
RUN DEBIAN_FRONTEND=noninteractive apt-get -q -y update

RUN DEBIAN_FRONTEND=noninteractive apt-get -q -y install cri-tools iproute2 ipvsadm procps iputils-arping

RUN DEBIAN_FRONTEND=noninteractive apt-get -q -y install python3 python3-kubernetes python3-requests

ADD app/ /opt/kubevs/
RUN rm -rf /opt/kubevs/lib.*
RUN find /opt/kubevs -name __pycache__ | while read F ; do rm -rfv $F ; done 

CMD sleep infinity
