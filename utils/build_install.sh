#!/bin/bash
#
# Compiles Android and updates a device.

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

nonEmptyVarOrExit "ANDROID_BUILD_TOP" "Need to set up Android build env first"
nonEmptyVarOrExit "OUT" "Need to set up Android build env first"

die () {
    echo "Failed" 1>&2
    exit -1
}

usage () {
    echo "usage: $(basename $0) [-i|-b] [DEVICESERIAL]"
    echo ""
    echo " -i: install only. Skips building."
    echo " -b: build only. Skips installing."
    echo " DEVICESERIAL: Targets serial number."
}

assertJavaCompilerVersion() {
    # Asserts current version of Java in the path.
    # Does not fail if Java is not in the path.
    which javac > /dev/null

    # Not in path.  Exit.
    if [[ $? != 0 ]]; then
        return 0
    fi

    # Grep for "1.6.".  Pass the return code through
    javac -version 2>&1 | grep "[^0-9]$1\." > /dev/null
    assert=$?

    if [[ $assert != 0 ]]; then
        printRed "JDK version $1 is required to continue."
        printRed "Please install JDK $1 or set \$JAVA_HOME"
        echo -n "Unacceptable JDK version found: "
        javac -version
    fi

    return $assert
}

getJavaHome() {
    echo $1 | grep "^[78]$" > /dev/null
    if [[ $? != 0 ]]; then
        echo Java version $1 is not supported.
        exit 1
    fi
    uname_system=$(uname -s)
    case "${uname_system}" in
        Darwin)
            /usr/libexec/java_home -v 1.$1 || (echo "Please install JVM version $1"; exit 1)
            ;;
        Linux)
            # Only support oracle-java
            java_home=/usr/lib/jvm/java-${1}-oracle/
            [[ -d "${java_home}" ]] || (echo "Please install java-$1-oracle"; exit 1)
            echo "${java_home}"
            ;;
        *)
            echo "Unsupported system ${uname_system}"
            exit 1
            ;;
    esac
}

install_only=0
build_only=0
while getopts "hibs" arg; do
    case "${arg}" in
        h)
            usage
            exit 1
            ;;
        i)
            install_only=1
            ;;
        b)
            build_only=1
            ;;
        *)
            usage
            exit 1
    esac
done
shift $((OPTIND-1))

if [[ ${build_only} == 1 ]] && [[ ${install_only} == 1 ]]; then
    printRed "Cannot enable build only (-b) and install only (-i) at the same time."
    exit 1
fi

# If we have an argument, check that it is a valid serial number we can pass
# to ADB to target a device.
ADB_CMD="adb"
if [[ ! -z "$1" ]]; then
    adb devices | grep -ve "^List of devices attached" | grep "${1}\t" > /dev/null
    if [ $? != 0 ]; then
        echo "Error: Device \"$1\" is not connected."
        exit 1
    fi

    ADB_CMD="adb -s $1"
fi

function adb-killall() {
    $ADB_CMD shell ps | grep "$1" | awk '{print $2}' | xargs $ADB_CMD shell kill
}

if [[ ${install_only} == 0 ]]; then
    cd "${ANDROID_BUILD_TOP}" &&

    assertJavaCompilerVersion 1.7 || exit 1

    # We need to source envsetup.sh to get the "mka" command
    export JAVA_HOME="$(getJavaHome 7)" &&
    . build/envsetup.sh >/dev/null &&

    # There are two types of targets: Packages and Modules.
    # For Packages, list them on their own line.
    # For Modules, list their dependent libraries first.  For example:
    #   [ LOCAL_JAVA_LIBRARIES ] [ LOCAL_STATIC_JAVA_LIBRARIES ] [ LOCAL_MODULE ]
    #
    # Please keep this list explicit, and include repeats.
    # This helps track what artifacts are actually needed.  (make will dedup)
    time mka host_out_binaries \
        android.policy conscrypt telephony-common services \
        framework-base framework \
        SystemUI \
        Settings

    build_rv=$?
    if [[ ${build_only} == 1 ]]; then
        if [[ ${build_rv} == 0 ]]; then
            printGreen "Build successfully completed."
        else
            printRed "Build failed! Exiting..."
            exit 1
        fi
    fi
fi

if [[ ${build_only} == 0 ]]; then
    UPDATE_FAILED=0

    cd "${ANDROID_BUILD_TOP}"

    # Cheap check that the phone is in recovery. (Also convert from dos-to-unix.)
    RO_TWRP_BOOT=$(adb shell getprop ro.twrp.boot | sed -e 's///g')
    if [[ "${RO_TWRP_BOOT}" != "1" ]]; then
        printRed "Error: Device must be in TWRP recovery!  After fixing, please rerun: "
        printRed " $0 -i"
        exit 1
    fi
    cd ${OUT} &&
    adb shell mount /system &&

    # Install platform
    for i in $(find system -type f); do
        echo "Installing ${i}..." &&

        # Priv-app system app needs to be pushed
        $ADB_CMD push "${OUT}/${i}" "/${i}"

        if [[ $? != 0 ]]; then
            UPDATE_FAILED=1
        fi
    done

    if [[ ${UPDATE_FAILED} == 1 ]]; then
        printRed "Failed to update phone.  It may be in a weird state now."
        exit 1
    else
        printGreen "Rebooting phone"
        adb reboot
        printGreen "Success!"
    fi
fi
