#!/bin/bash -e

set -o errexit -o nounset -o pipefail

BASEDIR=`dirname $0`/..

rm -rf \
    "$BASEDIR/.tox" \
    "$BASEDIR/env" \
    "$BASEDIR/build" \
    "$BASEDIR/dist" \
    $BASEDIR/*.egg-info

find . -name '*.pyc' | xargs rm -f
find . -name '__pycache__' | xargs rm -rf

echo "Deleted virtualenv and caches"
