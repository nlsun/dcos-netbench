#!/bin/bash
set -o errexit -o nounset -o pipefail

echo "CentOS tests are blocked on dcos-launch"
exit 1

$SHELL scripts/ci.sh \
    $CCM_AUTH_TOKEN \
    $BUILD_NUMBER \
    10 \
    "testing/master" \
    "N/A" \
    "centos" \
    "all" \
    "all"
