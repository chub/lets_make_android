#! /bin/bash

# Common constants, defaults, and helper methods

# Color printing
printGreen() {
    local COLOR="\033[32m"
    local RESET="\033[0m"
    echo
    echo -e "${COLOR}  $1 ${RESET}"
    echo
}

printRed() {
    local COLOR="\033[31m"
    local RESET="\033[0m"
    echo
    echo -e "${COLOR}  $1 ${RESET}"
    echo
}

printGreenStderr() {
    local COLOR="\033[32m"
    local RESET="\033[0m"
    echo 1>&2
    echo -e "${COLOR}  $1 ${RESET}" 1>&2
    echo 1>&2
}

printRedStderr() {
    local COLOR="\033[31m"
    local RESET="\033[0m"
    echo 1>&2
    echo -e "${COLOR}  $1 ${RESET}" 1>&2
    echo 1>&2
}

#
# Name / directory detection
#

# Preserve the original working dir as origDir.
origDir="${PWD}"

# Set progName to the program name and progDir to its directory.
# - When evaluating progName, follows all symlinks.
# - Note: Prepend PWD to $0 unless called with absolute path
if [[ "${0}" = /* ]]; then prog="${0}"; else prog="${PWD}/${0}"; fi
while [ -h "${prog}" ]; do
    prog=`readlink "${prog}"`
done

# chdir to the dirname to evaluate all the weird ../ and mounts
pushd `dirname "${prog}"` > /dev/null
progDir="${PWD}"
popd > /dev/null
progName=`basename "${prog}"`

unset prog

# Set rootDir to where this file lives.
# - Note: misbehaving callers can source us through a symlink.
rootBase=${BASH_SOURCE[0]}
while [ -h "${rootBase}" ]; do
    rootBase=`readlink "${rootBase}"`
done

pushd `dirname "${BASH_SOURCE[0]}"` > /dev/null
rootDir="${PWD}"
popd > /dev/null
unset rootBase

# Check that a variable is defined.
#
# Single argument usage assumes the environment was at fault.
# e.g.:  nonEmptyVarOrExit GERRIT_BRANCH
#
# Double argument usage assumes another issue.
# e.g.:  nonEmptyVarOrExit GERRIT_BRANCH "GERRIT_BRANCH must be defined."
function nonEmptyVarOrExit() {
    local varName=${1}
    local value=$(eval echo \$$varName)
    if [[ -z "${value}" ]]; then
        if [[ -z "${2}" ]]; then
            echo "Missing ${varName}. ${2}" 1>&2
        else
            echo "Missing ${varName}. Please check environment." 1>&2
            echo "" 1>&2
            echo "Environment dump:" 1>&2
            echo "=================" 1>&2
            env | sort 1>&2
        fi
        exit 1
    fi
}
