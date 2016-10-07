#!/bin/bash -e

BASEDIR=`dirname $0`/..
PROJNAME='dcos-netbench'

bootstrap() {
    source $BASEDIR/env/bin/activate
    echo "Virtualenv activated."

    pip install -r $BASEDIR/requirements.txt
    pip install -e $BASEDIR
    echo "Requirements installed."

    pip install tox
    echo "Tools installed."
}

if [ ! -d "$BASEDIR/env" ]; then
    virtualenv -p python3 -q $BASEDIR/env --prompt="(${PROJNAME}) "
    echo "Virtualenv created."

    bootstrap
elif [ ! -f "$BASEDIR/env/bin/activate" -o "$BASEDIR/setup.py" -nt "$BASEDIR/env/bin/activate" ]; then
    bootstrap
fi
