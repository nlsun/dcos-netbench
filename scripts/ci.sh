#!/bin/bash
set -o errexit -o nounset -o pipefail

status_line() {
    printf "\n### $1 ###\n\n"
}

run_tests() {
    CONFIG=$1
    OS=$2
    MASTERIP=$3
    REPS=$4
    TTYPE=$5
    NTYPE=$6
    PREFIX=$7

    TOKEN=$(python3 -c "import requests;js={'uid':'bootstrapuser', 'password': 'deleteme'};r=requests.post('http://"${MASTERIP}"/acs/api/v1/auth/login',json=js,);print(r.json()['token'])")

    echo "dcos_acs_token = \"$TOKEN\"" >> $CONFIG

    # The LC_ALL and LANG settings are because Python3 and Click are silly
    DCOS_CONFIG=$CONFIG \
        LC_ALL=C.UTF-8 \
        LANG=C.UTF-8 \
        $SHELL -c "source env/bin/activate && \
            python env/bin/dcos-netbench run $MASTERIP $OS --test $TTYPE --net $NTYPE --reps $REPS --prefix $PREFIX"
}

output_files() {
    for f in $@; do
        echo $f
        cat $f
        echo ""
    done
}

# The SSH key is expected to be in the SSH Agent already

CCM_AUTH_TOKEN=$1
BUILD_NUMBER=$2
TESTREPS=$3         # 5
DCOS_CHANNEL=$4     # "testing/master"
CF_TEMPLATE_NAME=$5 # "ee.single-master.cloudformation.json"
OS_TYPE=$6          # centos
TEST_TYPE=$7
NETWORK_TYPE=$8

TAGID="${OS_TYPE}${BUILD_NUMBER}"
CLUSTER_NAME="DCOSNETWORKPERF-${TAGID}"
CONFIG_PATH="/tmp/dcos_${TAGID}.toml"

status_line "Printing parameters"
shift # keep stuff hidden
echo $@

echo "$TAGID"
echo "$CLUSTER_NAME"
echo "$CONFIG_PATH"

status_line "Start CCM"
CLUSTER_ID=$(DCOS_CHANNEL=$DCOS_CHANNEL \
    CCM_AUTH_TOKEN=$CCM_AUTH_TOKEN \
    CLUSTER_NAME=$CLUSTER_NAME \
    CF_TEMPLATE_NAME=$CF_TEMPLATE_NAME \
    $SHELL ccm/start_ccm_cluster.sh)
echo "CLUSTER_ID $CLUSTER_ID"

status_line "Bootstrap"
make env

status_line "Wait CCM"
MASTERIP=$(CLUSTER_ID=$CLUSTER_ID \
    CCM_AUTH_TOKEN=$CCM_AUTH_TOKEN \
    $SHELL ccm/wait_for_ccm_cluster.sh)
echo "MASTERIP $MASTERIP"

status_line "Run tests"
DCOS_CONFIG=$CONFIG_PATH dcos config set core.dcos_url "http://$MASTERIP"
chmod 600 $CONFIG_PATH

run_tests "$CONFIG_PATH" \
    "$OS_TYPE" \
    "$MASTERIP" \
    "$TESTREPS" \
    "$TEST_TYPE" \
    "$NETWORK_TYPE" \
    "${TAGID}_"

status_line "Stop CCM"
CLUSTER_ID=$CLUSTER_ID \
    CCM_AUTH_TOKEN=$CCM_AUTH_TOKEN \
    $SHELL ccm/delete_ccm_cluster.sh

status_line "Printing results to stdout"
output_files ${TAGID}*.csv
