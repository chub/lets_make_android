#! /bin/bash
#
# Shared functions for APK builds.
# - Assumes gradle structure.
# - Assumes all release APKs are signed with the same release key.

# Check for required variables
nonEmptyVarOrExit "WORKSPACE"
nonEmptyVarOrExit "ANDROID_HOME"

function checkAndroidSdk() {
    local apiVersion=$1
    local buildToolsVersion=$2

    nonEmptyVarOrExit "apiVersion"
    nonEmptyVarOrExit "buildToolsVersion"

    printGreen "Checking Gradle dependencies"
    echo "Using build-tools version ${buildToolsVersion}"
    echo "Using API version ${apiVersion}"

    ./gradlew dependencies preBuild
    if [[ $? != 0 ]]; then
        printRed "Missing gradle dependencies.  Upgrading android SDK"
        (while :; do
            echo 'y'
            sleep 1
        done) | ${ANDROID_HOME}/tools/android update sdk --no-ui --all --filter android-${apiVersion},extra-android-m2repository,extra-google-m2repository,extra-android-support,extra-google-google_play_services,tools,platform-tools,build-tools-${buildTolsVersion}

        # Check again
        printGreen "Checking Gradle dependencies Take 2"
        ./gradlew dependencies
        if [[ $? != 0 ]]; then
            printRed "Dependencies are still missing, even after upgrading Android SDK."
            exit 1
        fi
    fi
}

function setPipelineMeta() {
    # Pipeline number to use (version of the source to start from)
    local pipelineNumber=$1
    # This git repo's name, from the context of the pipeline in question.
    local repoProject=$2

    # If pipelineNumber is specified, then grab the pipeline
    if [[ ! -z "${pipelineNumber}" ]] && [[ "${pipelineNumber}" != "manual" ]]; then
        S3_META_DIR=$(${rootDir}/utils/list_pipeline_meta.sh --pipeline_number=${pipelineNumber})
        echo "For P${pipelineNumber}, using S3_META_DIR ${S3_META_DIR}"
        nonEmptyVarOrExit "S3_META_DIR"

        mkdir ${WORKSPACE}/meta &&
        s3cmd get --recursive "${S3_META_DIR}" ${WORKSPACE}/meta &&
        if [[ ! -e ${WORKSPACE}/meta/repo-state.out ]]; then
            echo ""
            echo "########################################################"
            echo "Unknown pipeline number: \"${pipelineNumber}\"."
            echo "S3 directory is empty: ${S3_META_DIR}"
            echo "Build failed."
            echo "########################################################"
            echo ""
            exit 1
        fi &&

        COMMIT_HASH=$(${rootDir}/utils/repo_state_query.py --input_file=${WORKSPACE}/meta/repo-state.out ${repoProject}) &&
        printGreen "Checking out ${repoProject} ${COMMIT_HASH}" &&
        cd ${WORKSPACE} &&
        git checkout ${COMMIT_HASH}
    fi
}

function archiveApkToS3() {
    local moduleName=$1
    nonEmptyVarOrExit "moduleName"

    printGreen "archiving APK artifacts to S3 for module: ${moduleName}"

    # Publish every apk artifact
    cd ${WORKSPACE}/${moduleName}/build/outputs/apk && (tar -cf - \
       *.apk \
    ) | (mkdir -p ${WORKSPACE}/s3/apk && cd $_ && tar -xvf -)
}

function archiveProguardToS3() {
    local moduleName=$1
    nonEmptyVarOrExit "moduleName"

    printGreen "archiving Proguard artifacts to S3 for module: ${moduleName}"

    # Publish every proguard artifact
    if [[ -d ${WORKSPACE}/${moduleName}/build/outputs/mapping ]]; then
        cd ${WORKSPACE}/${moduleName}/build/outputs/mapping && (tar -cf - \
            * \
        ) | (mkdir -p ${WORKSPACE}/s3/mapping && cd $_ && tar -xvf -)
    fi
}
