#!/bin/bash
set -o errexit -o nounset -o pipefail

source scripts/ci_lib.sh

$SHELL scripts/ci.sh \
    $CCM_AUTH_TOKEN \
    $BUILD_NUMBER \
    10 \
    "testing/master" \
    "ee.single-master.cloudformation.json" \
    "coreos" \
    "all" \
    "overlay,host,bridge"

status_line "Pushing metrics to DataDog"

timestamp=$(currenttime)
httpfile=$(echo *http.csv)
redisfile=$(echo *redis.csv)

status_line "current time: $timestamp"

datadog $DATADOG_API_KEY $timestamp "coreos" "http95lat" "bridge" $(csv_val $httpfile 2)
datadog $DATADOG_API_KEY $timestamp "coreos" "http95lat" "host" $(csv_val $httpfile 3)
datadog $DATADOG_API_KEY $timestamp "coreos" "http95lat" "dcosoverlay" $(csv_val $httpfile 4)

datadog $DATADOG_API_KEY $timestamp "coreos" "redisget" "bridge" $(csv_val $redisfile 2)
datadog $DATADOG_API_KEY $timestamp "coreos" "redisget" "host" $(csv_val $redisfile 3)
datadog $DATADOG_API_KEY $timestamp "coreos" "redisget" "dcosoverlay" $(csv_val $redisfile 4)
