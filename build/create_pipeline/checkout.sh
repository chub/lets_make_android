#! /bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

nonEmptyVarOrExit "CLIENT_HOME"
nonEmptyVarOrExit "WORKSPACE"
nonEmptyVarOrExit "MANIFEST_BRANCH"
nonEmptyVarOrExit "MANIFEST_URL"

REPO_INIT_FLAGS=""
if [[ ! -z "${MANIFEST_FILE}" ]]; then
    REPO_INIT_FLAGS="${REPO_INIT_FLAGS} -m ${MANIFEST_FILE}"
fi

# Abort if the pipeline about to build a change newer than that of the gerrit trigger.
function abortIfStaleGerritTrigger() {
    # Return without abort on manual builds (GERRIT_EVENT_TYPE=="")
    if [[ "${GERRIT_EVENT_TYPE}" == "" ]] || [[ "${GERRIT_EVENT_TYPE}" != "change-merged" ]]; then
        echo "Not eligible for shortcut: GERRIT_EVENT_TYPE is \"${GERRIT_EVENT_TYPE}\""
        return
    fi

    # Do not continue if either GERRIT_PATCHSET_REVISION or GERRIT_PROJECT are missing
    if [[ "${GERRIT_PATCHSET_REVISION}" == "" ]]; then
        echo "Not eligible for shortcut: GERRIT_PATCHSET_REVISION is \"${GERRIT_PATCHSET_REVISION}\""
        return
    fi
    if [[ "${GERRIT_PROJECT}" == "" ]]; then
        echo "Not eligible for shortcut: GERRIT_PROJECT is \"${GERRIT_PROJECT}\""
        return
    fi

    # Find the path to the git repo
    REPO_PATH=$(repo forall -r "^${GERRIT_PROJECT}$" -c 'echo $REPO_PATH')
    if [[ "${REPO_PATH}" == "" ]]; then
        echo "Not eligible for shortcut: REPO_PATH for ${GERRIT_PROJECT} is \"$REPO_PATH\""
        return
    fi

    printGreen "Checking if ${REPO_PATH} ahead of ${GERRIT_PATCHSET_REVISION}"

    # Find the --git-dir
    if [[ ! -d "${REPO_PATH}" ]]; then
        # This is probably a mirror
        GIT_DIR="${GERRIT_PROJECT}.git"
    else
        GIT_DIR="${REPO_PATH}/.git"
    fi

    if [[ "${GERRIT_PATCHSET_REVISION}" != $(git --git-dir="${GIT_DIR}" rev-parse HEAD) ]]; then
        # Test using --is-ancestor
        git --git-dir="${GIT_DIR}" merge-base --is-ancestor ${GERRIT_PATCHSET_REVISION} HEAD

        # If exits successfully, then HEAD contains the commit.
        if [[ $? == 0 ]]; then
            printRed "HEAD of $REPO_PATH ($(git rev-parse HEAD)) is ahead of ${GERRIT_PATCHSET_REVISION}"
            printRed "Aborting since Gerrit Trigger event is stale"
            echo "GERRIT_PROJECT: ${GERRIT_PROJECT}"
            echo "GERRIT_PATCHSET_REVISION: ${GERRIT_PATCHSET_REVISION}"
            echo "GERRIT_EVENT_TYPE: ${GERRIT_EVENT_TYPE}"

            # Leave file for Jenkins to act on.
            touch "${WORKSPACE}/stale-gerrit-trigger.out"

            # The stale-gerrit-trigger.out file should convert this "exit 0" into an ABORT.
            # If the job is improperly configured, the build may continue to pass!
            exit 0
        fi
    fi
}

cd "${CLIENT_HOME}" && \
rm -vf .repo/local_manifests/*.xml && \
# Set the repo manifest
repo init -u "${MANIFEST_URL}" -b "${MANIFEST_BRANCH}" ${REPO_INIT_FLAGS} && \
# Cull unnecessary repo groups
case "$(uname -s)" in
    Darwin)
        repo init -g all,-notdefault,-mips,-x86,-eclipse,-linux
        ;;
    Linux)
        repo init -g all,-notdefault,-mips,-x86,-eclipse,-darwin
        ;;
    *)
        true
        ;;
esac &&

# Network sync with the triggered project.  Define the project paths to sync, but map
# them to project names in order to be compatible with repo mirror mode.
repo forall -c 'echo ${REPO_PATH} ${REPO_PROJECT}' | \
    cut -d ' ' -f 2- | \
    xargs repo sync -j4 &&

# Check if we can skip building this change
abortIfStaleGerritTrigger &&

# Sync other projects according to the manifest
# TODO(chub): Replace with mini_repo_sync.sh one day
repo sync &&

rm -f "${WORKSPACE}/repo-state.out" &&
${rootDir}/utils/repo_state_save.sh >> "${WORKSPACE}/repo-state.out"
