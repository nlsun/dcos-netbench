#!/bin/bash

# This script expects the following env var:
#   CLUSTER_NAME
#   CCM_AUTH_TOKEN
#   DCOS_CHANNEL
#   CF_TEMPLATE_NAME

set -e

# create cluster
CLUSTER_ID=$(http --ignore-stdin \https://ccm.mesosphere.com/api/cluster/ \
     Authorization:"Token ${CCM_AUTH_TOKEN}" \
     name=$CLUSTER_NAME \
     cloud_provider=0 \
     region=eu-central-1 \
     time=480 \
     channel=$DCOS_CHANNEL \
     cluster_desc="DC/OS CLI testing cluster" \
     template=$CF_TEMPLATE_NAME \
     adminlocation=0.0.0.0/0 \
     public_agents=0 \
     private_agents=2 | \
     jq ".id");

echo $CLUSTER_ID
