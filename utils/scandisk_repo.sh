#! /bin/bash
#
# Fixes a situation where repo is killed during a critical section, leaving
# repo projects and their git index in a zombie state.
#
# Intended to quickly rehab repo that may have entered this corrupted state.

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

nonEmptyVarOrExit "CLIENT_HOME"

function auditProject() {
    # Prints the state of the project.
    # Note: Use sparingly.  The output is noisy.
    cd "${CLIENT_HOME}/${REPO_PATH}" &&
    if [[ "$(git rev-parse HEAD)" != "${REPO_LREV}" ]]; then
        echo "${REPO_PATH}: [warn] currently at $(git rev-parse HEAD). Requested LREV ${REPO_LREV}."
    fi
}


# doFullSync pulls from the network and syncs the local git to what the manifest needs
# Call sparingly, since this process is slow (due to network speed) and brittle (when local
# projects have uncommited changes).
function doFullSync() {
    cd "${CLIENT_HOME}/${REPO_PATH}" &&
    echo "${REPO_PATH}: HEAD is at $(git rev-parse HEAD)" &&

    # 1. Download all remote changes
    cd "${CLIENT_HOME}" &&
    repo sync "${REPO_PATH}"

    if [[ $? != 0 ]]; then
        # 2. Reset working directory (so a checkout can safely occur)
        cd "${CLIENT_HOME}/${REPO_PATH}" &&
        git reset --hard
    fi
}

# Check for brain-dead/zombie situation.
# This occurs when $(repo sync -l) creates a skeleton, but incomplete git project.
cd "${CLIENT_HOME}/${REPO_PATH}" &&
# No redirection needed: git read-tree only prints on error (which is good)
git read-tree $REPO_LREV
if [[ $? != 0 ]]; then
    echo "${REPO_PATH}: Performing deep repair"
    cd "${CLIENT_HOME}" &&
    rm -r "${REPO_PATH}" ".repo/projects/${REPO_PATH}.git" &&
    # Checkout project, and sync to the manifest version
    repo sync -d "${REPO_PATH}"
    if [[ $? != 0 ]]; then
        echo "${REPO_PATH}: FAILED to perform deep repair"
        exit 1
    fi

    auditProject
fi

# Test if the gitspec is a reference.
echo $REPO_RREV | grep "^refs/" > /dev/null
if [[ $? == 0 ]]; then
    REV_IS_REF=1
else
    REV_IS_REF=0
fi

# Avoid doing a full sync.  Initialize to false.
NEED_FULL_SYNC=0

# If this is not a ref (and is a hard-coded commit hash)...
if [[ ${REV_IS_REF} == 0 ]]; then
    # then check if the directory is empty (which happens sometimes?)
    if [[ "$(ls | wc -l)" == 0 ]]; then
        echo "${REPO_PATH}: No files detected.  Resetting."
        git reset --hard
    fi

    # then check if project is already at the commit
    HEAD="$(git rev-parse HEAD)"
    if [[ "${HEAD}" != "${REPO_LREV}" ]]; then
        echo "${REPO_PATH}: HEAD is at ${HEAD}. Should be at ${REPO_LREV}."
        NEED_FULL_SYNC=1
    fi
fi

if [[ ${REV_IS_REF} == 1 ]] || [[ ${NEED_FULL_SYNC} == 1 ]]; then
    echo "${REPO_PATH}: Performing full sync due to REV_IS_REF=${REV_IS_REF} or NEED_FULL_SYNC=${NEED_FULL_SYNC}"
    echo "${REPO_PATH}: RREV=${REPO_RREV}, LREV=${REPO_LREV}"

    doFullSync

    RETURN_CODE=$?
    auditProject
    exit $RETURN_CODE
fi
