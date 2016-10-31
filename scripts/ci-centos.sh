#!/bin/bash
set -o errexit -o nounset -o pipefail

source scripts/ci_lib.sh




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

status_line "Pushing metrics to DataDog"

timestamp=$(currenttime)
httpfile=$(echo *http.csv)
redisfile=$(echo *redis.csv)

status_line "current time: $timestamp"

datadog $DATADOG_API_KEY $timestamp "centos" "http95lat" "bridge" $(csv_val $httpfile 2)
datadog $DATADOG_API_KEY $timestamp "centos" "http95lat" "dockeroverlay" $(csv_val $httpfile 3)
datadog $DATADOG_API_KEY $timestamp "centos" "http95lat" "host" $(csv_val $httpfile 4)
datadog $DATADOG_API_KEY $timestamp "centos" "http95lat" "dcosoverlay" $(csv_val $httpfile 5)

datadog $DATADOG_API_KEY $timestamp "centos" "redisget" "bridge" $(csv_val $redisfile 2)
datadog $DATADOG_API_KEY $timestamp "centos" "redisget" "dockeroverlay" $(csv_val $redisfile 3)
datadog $DATADOG_API_KEY $timestamp "centos" "redisget" "host" $(csv_val $redisfile 4)
datadog $DATADOG_API_KEY $timestamp "centos" "redisget" "dcosoverlay" $(csv_val $redisfile 5)
