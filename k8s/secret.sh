#!/bin/bash -e

if [ -z "$1" ] ; then
    echo "$(basename $0) DOMAIN-OF-KNODES" >&2
    exit 2
fi

# Check commands
if ! which openssl >/dev/null 2>&1 ; then
    echo " >>> openssl missing" >&2
    exit 1
fi

# Secret
cat <<EOF >/tmp/openssl.conf
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no
[req_distinguished_name]
CN = kubevs
[v3_req]
#basicConstraints = CA:FALSE
keyUsage = keyCertSign, keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = kubevs
DNS.2 = *.${1}
EOF

echo " >>> create ssl cert & key" >&2
openssl req -config /tmp/openssl.conf -x509 -newkey rsa:4096 -keyout /tmp/key.pem -out /tmp/cert.pem -days 36500 -nodes >&2

echo " >>> create auth token" >&2
openssl rand -base64 24 >/tmp/auth.token 

echo " >>> create secret" >&2
kubectl create --dry-run=client -o yaml secret generic helper-auth --from-file=cert=/tmp/cert.pem --from-file=key=/tmp/key.pem --from-file=token=/tmp/auth.token


# Cleanup
rm -rfv /tmp/{key.pem,cert.pem,auth.token} >&2
