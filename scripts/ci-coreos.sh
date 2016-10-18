#!/bin/bash
set -o errexit -o nounset -o pipefail

$SHELL scripts/ci.sh \
    $CCM_AUTH_TOKEN \
    $BUILD_NUMBER \
    5 \
    "testing/master" \
    "ee.single-master.cloudformation.json" \
    "coreos" \
    "all" \
    "overlay,host,bridge"
