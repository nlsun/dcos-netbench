#!/bin/bash
set -e

status_line() {
    printf "\n### $1 ###\n\n"
}

deploy_wait() {
    while dcos marathon deployment list > /dev/null 2>&1; do
        sleep 1
    done
}

send_ttracker() {
    port=$1
    hookmsg=$2

    dcos node ssh --option 'StrictHostKeyChecking=no' --leader --master-proxy \
        "\"curl -H \\\\\\\"Content-Type: application/json\\\\\\\" \
         -X PUT -d \\\\\\\"{\\\\\\\\\\\\\\\"value\\\\\\\\\\\\\\\": \\\\\\\\\\\\\\\"testnotify:$hookmsg\\\\\\\\\\\\\\\"}\\\\\\\" \
         127.0.0.1:$port/hook\""
 }

writejson() {
    tempfile=$1
    id=$2

cat << EOF > ${tempfile}
{
  "id": "/${id}",
  "cmd": "sleep 99h",
  "cpus": 0.02,
  "mem": 65,
  "disk": 0,
  "instances": 1,
  "container": {
    "docker": {
      "image": "alpine:3.3",
      "forcePullImage": false,
      "privileged": false,
      "network": "HOST"
    }
  },
  "portDefinitions": [
    {
      "protocol": "tcp",
      "port": 0
    }
  ]
}
EOF
}

#masterip=$1
#jsonpath=$1

numapps=$1

appbase="simpletest"
ttracker_port="38845"
tempfile=$(mktemp)
echo "tempfile: $tempfile"

# XXX make sure dcos cli is auth'd
# XXX run init ttracker

deploy_wait

status_line "Creating $numapps apps"
send_ttracker $ttracker_port "create_begin"

i=0
while [ $i -lt $numapps ]; do
    i=$((i + 1))
    appname="${appbase}${i}"
    writejson "$tempfile" "$appname"
    dcos marathon app add "$tempfile"
done
send_ttracker $ttracker_port "create_end"

status_line "Wait for create operation"
deploy_wait

status_line "Deleting apps"
send_ttracker $ttracker_port "delete_begin"

i=0
while [ $i -lt $numapps ]; do
    i=$((i + 1))
    appname="${appbase}${i}"
    dcos marathon app remove "$appname"
done
send_ttracker $ttracker_port "delete_end"

status_line "Wait for delete operation"
deploy_wait

rm "$tempfile"

# XXX run fetch ttracker
