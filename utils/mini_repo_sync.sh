#! /bin/bash
#
# Minimal sync for building CM using build-install
#
# By default:
# - Avoid syncing kernel/ repos since they are not needed by build-install

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

usage () {
    echo "usage: $(basename $0) [-h] [-n] [-D]"
    echo ""
    echo "Syncs the minimum number of repos for build-install"
    echo ""
    echo " -D: skip syncing device/* repos"
    echo " -h: display usage"
}

include_device_repos=1
total_repos=2
while getopts "hnD" arg; do
    case "${arg}" in
        h)
            usage
            exit 1
            ;;
        D)
            include_device_repos=0
            total_repos=$((total_repos-1))
            ;;
        *)
            usage
            exit 1
    esac
done
shift $((OPTIND-1))

repo_count=1

# Find repo root
function findRepoRoot() {
    startDir=${PWD}
    count=0
    maxCount=30

    while [[ "${PWD}" != "/" ]]; do
        if [[ -d .repo ]]; then
            echo "${PWD}"
            cd ${startDir}
            return
        fi

        # Protect against infinite loops
        if [[ $count > $maxCount ]]; then
            echo "Cannot find repo root after ${maxCount} chdirs from ${startDir}.  Exiting." 1>&2
            exit 1
        fi
        count=$((count+1))

        # Go up
        cd ..
    done

    echo "Unable to find Android root. Exiting." 1>&2
    exit 1
}

repoRoot=$(findRepoRoot)
if [[ $? != 0 ]]; then
    exit 1
fi

cd $(findRepoRoot) &&

if [[ ${include_device_repos} == 1 ]]; then
    printGreen "Repo [${repo_count}/${total_repos}]: Syncing Device repos"
    repo_count=$((repo_count+1))

    time repo forall -r android_device -c 'echo $REPO_PROJECT' | xargs repo sync -d
fi &&

printGreen "Repo [${repo_count}/${total_repos}]: Syncing CM repos"
repo_count=$((repo_count+1))
time repo sync -d \
    abi/cpp \
    bionic \
    build \
    dalvik \
    external/android-visualizer \
    external/apache-http \
    external/bison \
    external/bouncycastle \
    external/clang \
    external/compiler-rt \
    external/expat \
    external/fdlibm \
    external/icu4c \
    external/junit \
    external/libphonenumber \
    external/libpng \
    external/llvm \
    external/nist-sip \
    external/okhttp \
    external/openssl \
    external/proguard \
    external/protobuf \
    external/stlport \
    external/tagsoup \
    external/zlib \
    frameworks/native \
    frameworks/opt/net/voip \
    frameworks/opt/telephony \
    frameworks/support \
    libcore \
    libnativehelper \
    prebuilts/misc \
    prebuilts/ndk \
    prebuilts/sdk \
    system/core \
    vendor/cm
