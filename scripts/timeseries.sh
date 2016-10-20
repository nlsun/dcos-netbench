#!/bin/bash

# You can use a `cut`-like column syntax but then the separator doesn't work well

# Sample Run:
# bash scripts/timeseries.sh manyruns2 _redis.csv 2,3,4,5 ', '

source_dir=$1
postfix=$2
column=$3
separator=$4

if [ $# -ne 4 ]; then
    echo "Invalid number of arguments"
    exit 1
fi

title=$(cat $(echo $source_dir/*$postfix | head -n1) | head -n1 | cut -f$3 -d',')
echo "Timestamp${separator}${title}"

for file in $source_dir/*$postfix; do
    timestamp=$(basename $file | cut -f1 -d'_')
    val=$(cat $file | tail -n +2 | cut -f$3 -d',')
    echo "${timestamp}${separator}${val}"
done
