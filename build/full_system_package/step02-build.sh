#! /bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../../shell_base.sh

# Check for required variables
nonEmptyVarOrExit "CLIENT_HOME"
nonEmptyVarOrExit "DEVICE_NAME"
nonEmptyVarOrExit "WORKSPACE"

nonEmptyVarOrExit "MANIFEST_URL"
nonEmptyVarOrExit "MANIFEST_BRANCH"

function initRepo() {
    printGreen "[ INITING REPO ]" &&
    cd ${CLIENT_HOME} &&

    repo init -u ${MANIFEST_URL} -b ${MANIFEST_BRANCH} &&
    repo init -p linux -g all,-notdefault,-mips,-x86,-eclipse,-darwin
}

function setPipelineMeta() {
    # If PIPELINE_NUMBER is specified, then grab the pipeline
    if [[ ! -z "${PIPELINE_NUMBER}" ]] && [[ "${PIPELINE_NUMBER}" != "manual" ]]; then
        printGreen "[ SYNCING ] Restoring pipeline state to P${PIPELINE_NUMBER}" &&

        S3_META_DIR=$(${rootDir}/utils/list_pipeline_meta.sh --pipeline_number=${PIPELINE_NUMBER})
        echo "For P${PIPELINE_NUMBER}, using S3_META_DIR ${S3_META_DIR}"
        nonEmptyVarOrExit "S3_META_DIR"

        mkdir ${WORKSPACE}/meta &&
        s3cmd get --recursive "${S3_META_DIR}" ${WORKSPACE}/meta &&
        if [[ ! -e ${WORKSPACE}/meta/repo-state.out ]]; then
            echo ""
            echo "########################################################"
            echo "Unknown pipeline number: \"${PIPELINE_NUMBER}\"."
            echo "S3 directory is empty: ${S3_META_DIR}"
            echo "Build failed."
            echo "########################################################"
            echo ""
            false
        fi &&

        # Sync projects in the PIPELINE
        cd ${CLIENT_HOME} &&
        # Checkout specific commit for all known projects
        ${rootDir}/utils/repo_state_restore.sh \
            < ${WORKSPACE}/meta/repo-state.out
    fi
}

function syncRepo() {
    # Update manifest repo
    cd ${CLIENT_HOME} &&
    printGreen "[ SYNCING ] Updating manifest..." &&
    if [[ -d .repo/manifests ]]; then
        cd .repo/manifests &&
        git pull
    else
        printRed "[ SYNCING ] WARNING: manifest was not updated."
        # Maybe do a repo init?
    fi &&

    cd ${CLIENT_HOME} &&

    # TODO(chub): Replace with mini-repo-sync one day.
    printGreen "[ SYNCING ] Updating repo..." &&
    # Capture stderr from repo sync (but still display stderr on screen)
    set +o noclobber &&
    rm -vf ${WORKSPACE}/repo-sync.stderr &&
    repo sync 2> >(tee ${WORKSPACE}/repo-sync.stderr >&2)
    if [[ $? != 0 ]]; then
        # If repo sync failed, re-print stderr AND THEN FAIL THE FUNCTION
        printRed "Contents of previous repo stderr"
        echo "=============="
        cat ${WORKSPACE}/repo-sync.stderr
        echo "=============="
        false
    fi &&

    setPipelineMeta &&

    printGreen "[ SYNCING ] Archiving the full repo state for this build..." &&
    mkdir -p ${WORKSPACE}/s3_device &&
    ${rootDir}/utils/repo_state_save.sh > ${WORKSPACE}/s3_device/repo-state.out
}

function clearOldBuilds() {
    printGreen " [ CLEAR OLD BUILDS ] Checking for old builds"

    # Remove target-files if there are files inside
    if [[ ! -z $(ls $OUT/obj/PACKAGING/target_files_intermediates/ 2> /dev/null) ]]; then
        ls "${OUT}/obj/PACKAGING/target_files_intermediates/" &&
        printGreen " [ CLEAR OLD BUILDS ] Removing old target_files_intermediates" &&
        rm -rf "${OUT}/obj/PACKAGING/target_files_intermediates"
    fi &&

    # Remove last FOTA
    ls ${OUT}/*.zip* > /dev/null 2>&1
    if [[ $? == 0 ]]; then
        printGreen " [ CLEAR OLD BUILDS ] Removing old OTA" &&
        rm -fv ${OUT}/*.zip*
    fi &&

    # Remove all the build props (which is necessary for fcm to properly identify different builds)
    if [[ -d ${OUT} ]]; then
        printGreen " [ CLEAR OLD BUILDS ] Finding and removing old prop files" &&
        find ${OUT} -type f -name *.prop -exec rm -v {} \;
    fi
}

function prepareOut() {
    cd ${CLIENT_HOME} &&

    # Quit if out/ is a directory or a random file
    if [[ -e out ]]; then
        if [[ ! -L out/host ]] || [[ ! -L out/target ]]; then
            printRed " [ OUT ] out/ skeleton is corrupt (since it does not have constituent host and target destinations).  Please decompose into host and target, or remove." &&
            ls -la out/ &&
            false
        fi
    fi &&

    # If out does not exist, then create everything
    mkdir -p out/ &&
    if [[ -L out/host ]]; then
        rm -v out/host
    fi &&
    if [[ -L out/target ]]; then
        rm -v out/target
    fi &&
    mkdir -p out_host &&
    mkdir -p "out_target_${DEVICE_NAME}" &&
    cd out/ &&
    ln -s ../out_host/ host &&
    ln -s ../out_target_${DEVICE_NAME}/ target
}

function buildFota() {
    cd ${CLIENT_HOME} &&
    if [[ ! -z "${PIPELINE_NUMBER}" ]]; then
        printGreen "[ BUILD ] Setting PIPELINE ${PIPELINE_NUMBER} into TARGET_UNOFFICIAL_BUILD_ID" &&
        export TARGET_UNOFFICIAL_BUILD_ID=P${PIPELINE_NUMBER}
    fi &&
    printGreen "[ BUILD ] Sourcing envsetup" &&
    . build/envsetup.sh &&

    if [[ -e vendor/cm/vendorsetup.sh ]]; then
        printGreen "[ BUILD ] Calling breakfast for ${DEVICE_NAME}" &&
        breakfast ${DEVICE_NAME}
    else
        printGreen "[ BUILD ] Calling lunch aosp_${DEVICE_NAME}-userdebug" &&
        lunch aosp_${DEVICE_NAME}-userdebug
    fi &&

    clearOldBuilds &&

    if [[ -e vendor/cm/vendorsetup.sh ]]; then
        printGreen "[ BUILD ] Executing mka bacon" &&
        time mka bacon
    else
        printGreen "[ BUILD ] Executing mka otapackage" &&
        time mka otapackage
    fi
}

function generateBuildManifest() {
    # Save this build's manifest
    cd ${CLIENT_HOME} &&
    mkdir -p ${WORKSPACE}/s3_device/bin/system/etc &&
    repo manifest -r -o ${WORKSPACE}/s3_device/bin/system/etc/build-manifest.xml
}

# zip files, etc.
function gatherArtifactsDevice() {
    # If there is a CM ROM, archive it (and any associated .md5sum files)
    # Also filter by TARGET_UNOFFICIAL_BUILD_ID (which may be empty) in the filename.
    ls ${OUT}/cm-*${TARGET_UNOFFICIAL_BUILD_ID}*.zip* > /dev/null 2>&1
    if [[ $? == 0 ]]; then
        cd ${OUT} && (tar -cf - \
            cm-*${TARGET_UNOFFICIAL_BUILD_ID}*.zip* \
            ) | (mkdir -p ${WORKSPACE}/s3_device/rom && cd $_ && tar -xvf -)
    fi

    # Filter out all Cyanogen targets
    if [[ ! "${TARGET_PRODUCT}" =~ ^cm_ ]]; then
        # If there is an AOSP ROM, archive it too.
        ls ${OUT}/${TARGET_PRODUCT}*.zip* > /dev/null 2>&1
        if [[ $? == 0 ]]; then
            cd ${OUT} && (tar -cf - \
                ${TARGET_PRODUCT}*.zip* \
                ) | (mkdir -p ${WORKSPACE}/s3_device/rom && cd $_ && tar -xvf -)

        fi
    fi
}

printGreen "Jenkins Stage: initing repo" &&
initRepo ||
( printRed "Jenkins Stage: initing repo FAILED" ; false ) &&

printGreen "Jenkins Stage: preparing OUT" &&
prepareOut ||
( printRed "Jenkins Stage: preparing OUT FAILED" ; false ) &&

printGreen "Jenkins Stage: syncing repo" &&
syncRepo ||
( printRed "Jenkins Stage: syncing repo FAILED" ; false ) &&

printGreen "Jenkins Stage: building" &&
buildFota ||
( printRed "Jenkins Stage: building FAILED" ; false ) &&

printGreen "Jenkins Stage: generating new build-manifest.xml" &&
generateBuildManifest  ||
( printRed "Jenkins Stage: generating new build-manifest.xml FAILED" ; false ) &&

printGreen "Jenkins Stage: gathering artifacts for device" &&
gatherArtifactsDevice  ||
( printRed "Jenkins Stage: gathering artifacts for device FAILED" ; false ) &&

printGreen "Jenkins Stage: done gathering artifacts"
