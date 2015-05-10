#! /bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

# Check that we are in a repo root
if [[ ! -e .repo/manifest.xml ]]; then
    echo "ERROR: Current working directory (`pwd`) is not a repo root."
    exit 1
fi

# Expect the following STDIN format:
#   project_path
#   project_sha to checkout
#   ...

SOMETHING_FAILED=0
PROJECT_PATH=""
PROJECT_SHA1=""
OLD_PWD=${PWD}

# Contains a list of inclusive directories to operate on.
# When non-empty, all repo project path must be included to be processed.
DIR_FILTERS=$@

function argsContainsDir() {
    NEEDLE=$1

    for arg in ${DIR_FILTERS}; do
        if [[ ${NEEDLE} == ${arg} ]]; then
            return 0
        fi
    done

    # Did not find path
    return 1
}

while read line; do
    if [[ -z ${PROJECT_PATH} ]]; then
        PROJECT_PATH=${line}
    else
        PROJECT_SHA1=${line}

        SKIP_PROJECT=0

        # If we were called with arguments, then filter project directories.
        if [[ $# -gt 0 ]]; then
            argsContainsDir ${PROJECT_PATH}
            if [[ $? != 0 ]]; then
                SKIP_PROJECT=1
            fi
        fi

        # Check if the project path actually exists
        if [[ ${SKIP_PROJECT} == 0 ]]; then
            if [[ ! -d "${PROJECT_PATH}" ]]; then
                echo "missing: ${PROJECT_PATH}. Skipping"
                SKIP_PROJECT=1
            fi
        fi


        if [[ ${SKIP_PROJECT} == 0 ]]; then
            echo "project ${PROJECT_PATH}"
            if [[ `cat ${PROJECT_PATH}/.git/HEAD` != ${PROJECT_SHA1} ]]; then
                cd ${PROJECT_PATH} &&
                git checkout ${PROJECT_SHA1}
            else
                echo "already at ${PROJECT_SHA1}"
            fi

            if [[ $? != 0 ]]; then
                printRed "Could not reset ${PROJECT_PATH} to ${PROJECT_SHA1}"
                SOMETHING_FAILED=1
            fi

            # Reset directory
            cd ${OLD_PWD}
            if [[ $? != 0 ]]; then
                # Wow, this sucks.
                printRed "Could not return to outer directory"
                SOMETHING_FAILED=1
            fi
        else
            if [[ "${VERBOSE}" == 1 ]] || [[ "${VERBOSE}" == "true" ]]; then
                # Set VERBOSE to debug no-ops. (The line is usually not informative.)
                echo "skipping project ${PROJECT_PATH}"
            fi
        fi

        # Reset vars for next pair
        PROJECT_PATH=""
        PROJECT_SHA1=""
    fi
done

exit $SOMETHING_FAILED
