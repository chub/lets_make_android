#! /bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../../shell_base.sh

# Check for required variables
nonEmptyVarOrExit "CLIENT_HOME"
nonEmptyVarOrExit "DEVICE_NAME"
nonEmptyVarOrExit "WORKSPACE"

# Global variables
DIST_NAME=

function lookupDistName() {
    DIST_NAME=$(${rootDir}/list_pipeline_meta.sh --pipeline_number=${PIPELINE_NUMBER} --showdist)
    if [[ "${DIST_NAME}" == "" ]]; then
        printRed "Unable to find DIST_NAME for P${PIPELINE_NUMBER}"
        return 1
    fi
    echo "Using P${PIPELINE_NUMBER}/${DIST_NAME}"
}

function checkPipelineAndDistSettings() {
    # If Pipeline is set and is "manual," the distribution should be master.
    # Any other setting is an error.
    if [[ ! -z "${PIPELINE_NUMBER}" ]] && [[ ! -z "${DIST_NAME}" ]]; then
        if [[ "${PIPELINE_NUMBER}" == "manual" ]] && [[ "${DIST_NAME}" != "master" ]]; then
            printRed "For Pmanual, DIST_NAME must be master.  DIST_NAME is currently ${DIST_NAME}."
            printRed "Continuing may cross builds between distributions.  Exiting."
            exit 1
        fi
    fi
}

printGreen "looking up DIST_NAME" &&
lookupDistName &&

printGreen "Checking Pipeline and Distribution settings" &&
checkPipelineAndDistSettings
