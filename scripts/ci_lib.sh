#!/bin/bash

status_line() {
    printf "\n### $1 ###\n\n"
}

# Extract a value from a CSV
csv_val() {
    file=$1
    column=$2

    cat "$file" | tail -n +2 | cut -d',' -f"${column}"
}

currenttime() {
    echo $(date +%s)
}

# Send network performance metrics to datadog
datadog() {
    datadogkey=$1
    timestamp=$2
    os=$3
    testtype=$4
    perftype=$5
    value=$6

    curl -X POST -H "Content-type: application/json" \
    -d "{ \"series\" :
            [{\"metric\":\"dcos.network.perf.${os}.${testtype}.${perftype}\",
              \"points\":[[$timestamp, $value]],
              \"type\":\"gauge\",
              \"tags\":[\"perfgroup:dcosnet\"]}]}" \
    "https://app.datadoghq.com/api/v1/series?api_key=$datadogkey"
}

