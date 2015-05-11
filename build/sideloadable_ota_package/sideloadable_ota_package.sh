#! /bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../../shell_base.sh

nonEmptyVarOrExit "CLIENT_HOME"
nonEmptyVarOrExit "DEVICE_NAME"
nonEmptyVarOrExit "WORKSPACE"
nonEmptyVarOrExit "PIPELINE_NUMBER"

DIST_NAME=

lookupDistName() {
    DIST_NAME=$(${rootDir}/utils/list_pipeline_meta.sh --pipeline_number=${PIPELINE_NUMBER} --showdist)
    if [[ "${DIST_NAME}" == "" ]]; then
        printRed "Unable to find DIST_NAME for P${PIPELINE_NUMBER}"
        return 1
    fi
    printGreen "Using DIST_NAME ${DIST_NAME}"
}

downloadDeviceArtifacts() {
    # s3://BUCKET/files/devices/BRANCH/common/B38-P17--2014-05-20_02-26-38--cm_hammerhead-userdebug/
    S3_PATH=$(${rootDir}/utils/list_builds.sh --device=${DEVICE_NAME} --pipeline_number=${PIPELINE_NUMBER} --dist=${DIST_NAME} --numrows=1)
    if [[ -z "${S3_PATH}" ]]; then
        echo "device artifacts not found."
        return 1
    fi

    # Only download bin subdir
    S3_PATH="${S3_PATH}bin/"

    printGreen "Selected S3 dir: ${S3_PATH}"

    s3cmd get --recursive "${S3_PATH}" ${WORKSPACE}/zip
}

copyDeviceArtifacts() {
    # chdir to ensure the directory exists (build should fail if it does not exist)
    cd "${WORKSPACE}/s3_device/bin" &&
    rsync -vPra ${WORKSPACE}/s3_device/bin/ ${WORKSPACE}/zip
}

downloadSystemAppArtifacts() {
    # s3://BUCKET/files/clients/NAME_OF_GRADLE_APP_PROJECT/BRANCH/B783-P839--2014-09-11_21-05-12/apk/sdk_app-debug.apk
    #
    # TODO: convert this to use --artifact=$1 and basename from the result.
    S3_PATH=$(${rootDir}/utils/list_builds_client.sh --artifact=sdk_app-debug.apk --pipeline_number=${PIPELINE_NUMBER} --dist=${DIST_NAME} --numrows=1)
    if [[ -z "${S3_PATH}" ]]; then
        echo "sdk_app artifacts not found."
        return 1
    fi

    # Only download .apk object.
    printGreen "sdk_app artifacts: ${S3_PATH}"

    APK_NAME=$1

    # Install APK
    mkdir -p ${WORKSPACE}/zip/system/app &&
    ${rootDir}/utils/s3cmd get --recursive "${S3_PATH}" ${WORKSPACE}/zip/system/app/${APK_NAME}.apk
    if [[ $? != 0 ]]; then
        echo "Unable to download ${APK_NAME}.apk from S3."
        return 1
    fi

    printGreen "Extracting any JNI files within sdk_app"

    # Extract JNI libraries into /system/lib
    # Use the device's build.prop to detect the device architecture
    DEVICE_ARCH=$(grep ^ro.product.cpu.abi= "${WORKSPACE}/s3_device/bin/system/build.prop" | cut -d '=' -f 2)
    if [[ "${DEVICE_ARCH}" == "" ]]; then
        echo "Unable to determine architecture for device \"${DEVICE_NAME}\". Cannot properly install JNI."
        return 1
    fi

    # Unzip JNI directories
    mkdir -p ${WORKSPACE}/apk_jni &&
    # unzip(1) returns 0 if successful, 11 if "no matching files were found"
    unzip -d ${WORKSPACE}/apk_jni ${WORKSPACE}/zip/system/app/${APK_NAME}.apk "lib/${DEVICE_ARCH}/*" &&
    UNZIP_RV=$?

    case "$?" in
        0)
            mkdir -p ${WORKSPACE}/zip/system/lib/ &&
            rsync -vPra ${WORKSPACE}/apk_jni/lib/${DEVICE_ARCH}/ $_
            ;;
        11)
            printRed "warning: No JNI libraries found. Continuing."
            ;;
        *)
            printRed "error: unzip returned unknown error code $?"
            return 1
            ;;
    esac
}

printGreen "Jenkins Stage: looking up DIST_NAME" &&
lookupDistName || (printRed "FAILED"; false) &&

mkdir -p "${WORKSPACE}/zip" &&

#printGreen "Jenkins Stage: downloading device artifacts" &&
#downloadDeviceArtifacts || (printRed "FAILED"; false) &&

printGreen "Jenkins Stage: copying device artifacts" &&
copyDeviceArtifacts || (printRed "FAILED"; false) &&

printGreen "Jenkins Stage: downloading sdk_app artifacts" &&
downloadSystemAppArtifacts sdk_app || (printRed "FAILED"; false) &&

mkdir -p "${WORKSPACE}/s3_device/ota" &&
cd ${CLIENT_HOME} &&
PYTHONPATH="${CLIENT_HOME}/build/tools/releasetools" \
  ${rootDir}/build/sideloadable_ota_package/build_delta_ota \
  -d "${WORKSPACE}/zip/" \
  -b "${rootDir}/build/sideloadable_ota_package/ota-begin-script.edify" \
  -e "${rootDir}/build/sideloadable_ota_package/ota-extra-script.edify" \
  --path "${rootDir}/utils/binaries" \
  --signapk_path host/signapk.jar \
  "${WORKSPACE}/s3_device/ota/sideload.zip"
