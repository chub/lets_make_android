#! /bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

nonEmptyVarOrExit "CLIENT_HOME"

GREEN="\033[32m"
RED="\033[31m"
RESET="\033[0m"

cd "${CLIENT_HOME}"

function scandisk() {
    # Scandisk, because this is really fast and can still give false positives.
    repo forall -c "CLIENT_HOME=${CLIENT_HOME} ${rootDir}/utils/scandisk_repo.sh"
}

function rmRoomService() {
    # Remove roomservice.xml to avoid duplicate project declarations
    # If roomservice really is needed, breakfast/brunch/mkabacon will re-list the missing projects.
    if [[ -e .repo/local_manifests/roomservice.xml ]]; then
        echo -e "${GREEN} Possible manifest.xml change. Removing roomservice.xml ${RESET}"
        rm -v .repo/local_manifests/roomservice.xml
    fi
}

# First try repo-syncing locally
echo -e "${GREEN} [FAST#1] syncing repo ${RESET}"
repo sync -l
FIRST_SYNC_RESULT=$?

# If first command succeeds, verify every project has tree information about the revision they should be on.
if [[ ${FIRST_SYNC_RESULT} == 0 ]]; then
    echo -e "${GREEN} [FAST#2] running scandisk ${RESET}"
    rmRoomService
    scandisk
fi

# If first command fails (or if scandisk fails), then continue with a heavier repair.
if [[ $? != 0 ]] || [[ ${FIRST_SYNC_RESULT} != 0 ]]; then
    rmRoomService
    echo -e "${GREEN} [SLOW#2] git reset all projects ${RESET}"
    repo forall -c "git reset --hard"
    echo -e "${GREEN} [SLOW#2] syncing repo ${RESET}"
    repo sync
fi

# If full sync fails, try scandisk and another local sync.
if [[ $? != 0 ]]; then
    echo -e "${GREEN} [SLOW#3] syncing repo to manifest version ${RESET}"
    # This is a hack to deal with repo not handling post-(repo sync -l) commands properly
    scandisk

    # Quick test
    echo -e "${GREEN} [FAST#4] syncing repo to manifest version ${RESET}"
    repo sync -l
fi
