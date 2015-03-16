#! /bin/bash

SCRIPT_DIR="$(dirname $0)"
SRC_DIR="$(readlink -e ${SCRIPT_DIR}/..)"
DEST="/tmp/iot-lab-gateway"

# options

verbose=0
SSH_OPT="-F $(readlink -e ${SCRIPT_DIR}/ssh_config)"
tests_only=0
sync_only=0
TESTS_ARGS=''
GATEWAY_HOSTNAME=

usage()
{
    cat << EOF
Usage: ${0##*/} [-hv] [-s] [-t] <GATEWAY_HOSTNAME>
Run the integrations tests on GATEWAY_HOSTNAME.
    -T TEST_LIST Run these tests (comma-separated list)
    -t          run only python tests
    -s          sync code only and exit
    -h          display this help and exit
    -v          verbose mode

Example for TEST_LIST:
    gateway_code.integration.tests_integration:TestComplexExperimentRunning.test_simple_experiment
EOF
}

parse_arguments()
{
    local OPTIND=1
    while getopts "hvstT:" opt; do
        case "$opt" in
            T) TESTS_ARGS="--tests=$OPTARG"
                ;;
            h) usage
                exit 0
                ;;
            v) verbose=1
                ;;
            t) tests_only=1
                ;;
            s) sync_only=1
                ;;
            '?')
                usage >&2
                exit 1
                ;;
        esac
    done
    shift "$((OPTIND-1))"  # shift off the options and optional --
    if [[ $# != 1 ]]; then
        echo "No GATEWAY_HOSTNAME provided" >&2
        usage >&2
        exit 1
    fi
    GATEWAY_HOSTNAME="$1"
}

parse_arguments $@

if [[ 1 -eq $verbose ]]; then
    echo "Verbose output"
    echo "GATEWAY_HOSTNAME: ${GATEWAY_HOSTNAME}"
    echo "tests_only: ${tests_only}"
    set -x
fi

date
set -e

# update host with www-data:www-data as owner
rsync -e "ssh ${SSH_OPT}" -av --delete --exclude='gateway_code.egg-info' \
    --exclude='obj' --exclude='tests/bin' --exclude='tests/results'      \
    --exclude='*pyc' --exclude='cover' --exclude='.git' --exclude='.tox' \
    ${SRC_DIR}/   ${GATEWAY_HOSTNAME}:${DEST}
set +e

ssh ${SSH_OPT} ${GATEWAY_HOSTNAME} "chown -R www-data:www-data ${DEST}"

if [[ 1 -eq ${sync_only} ]]; then
    exit 0
fi



if [[ 1 -eq ${tests_only} ]]; then
    # Run only python tests
    ssh ${SSH_OPT} ${GATEWAY_HOSTNAME} "su www-data -c '\
        source /etc/profile; \
        killall python socat control_node_serial_interface; \
        cd ${DEST};
        tox -e test'"
else
    # Run all tests, python, style checker, C code tests

    ssh ${SSH_OPT}   ${GATEWAY_HOSTNAME} "su www-data -c '\
        source /etc/profile; \
        killall python socat control_node_serial_interface; \
        cd ${DEST};
        tox -e integration'"

    # run control_node_serial tests
    ssh ${SSH_OPT}   ${GATEWAY_HOSTNAME} "\
        source /etc/profile; \
        make -C ${DEST}/control_node_serial realclean coverage"
fi

#
# Get results files
#
rsync -e "ssh ${SSH_OPT}" -av \
    --exclude='.tox' --exclude='*egg' --include='*/' --include='*xml' --include='*out' --exclude='*'  -av \
    ${GATEWAY_HOSTNAME}:${DEST}/ ${SRC_DIR} | grep -v "sender"

exit 0
