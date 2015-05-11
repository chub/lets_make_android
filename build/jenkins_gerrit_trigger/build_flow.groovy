//////////////// Common functions Start

def test_build_system_images(gerrit_project) {
    // In AOSP, device repos start with device- and frameworks start with platform-.
    // Include cyanogen- prefix for good measure.
    regex = /^(platform-|android-|cyanogen-|device-).*/
    matcher = (gerrit_project =~ regex)
    if (matcher.matches()) {
        println "build_system_images is True"
        return true
    }
    return false
}

//////////////// Common functions End

def manifest_url = build.environment.get("MANIFEST_URL", "")
def manifest_branch = build.environment.get("MANIFEST_BRANCH", "")
def manifest_file = build.environment.get("MANIFEST_FILE", "")

def job_name_repo_mirror = build.environment.get("JOB_NAME_REPO_MIRROR", "__unset__")
def job_name_repo_reference = build.environment.get("JOB_NAME_REPO_REFERENCE", "__unset__")
def slave_node_repo_mirror = build.environment.get("SLAVE_NODE_REPO_MIRROR", "__unset__")
def slave_node_repo_reference = build.environment.get("SLAVE_NODE_REPO_REFERENCE", "__unset__")

def gerrit_topic = build.environment.get("GERRIT_TOPIC", "")
if (gerrit_topic == "") {
    gerrit_topic = "_default"
}
def gerrit_branch = build.environment.get("GERRIT_BRANCH", "")
if (gerrit_branch == "") {
    gerrit_branch = "master"
}
// No default for empty gerrit_project
def gerrit_project = build.environment.get("GERRIT_PROJECT", "")

// Set the manifest branch if not already set
def manifest_branch = build.environment.get("MANIFEST_BRANCH", "__unset__")
if (manifest_branch == "__unset__") {
    manifest_branch = "master"
}

def dist_name = build.environment.get("DIST_NAME", "__unset__")
if (dist_name == "__unset__") {
    dist_name = "master"
}

def build_system_images = test_build_system_images(gerrit_project)

//////////////// Build start

if (!build_system_images) {
    println "No builds triggered.  This job will now exit."
} else {
    build(job_name_repo_mirror,
        PIPELINE_NUMBER:build.number,
        DIST_NAME:dist_name,
        MANIFEST_URL:manifest_url,
        MANIFEST_BRANCH:manifest_branch,
        MANIFEST_FILE:manifest_file,
        SLAVE_NODE:slave_node_repo_mirror,
        GERRIT_PATCHSET_REVISION:build.environment.get("GERRIT_PATCHSET_REVISION", ""),
        GERRIT_PROJECT:gerrit_project,
        GERRIT_BRANCH:gerrit_branch,
        GERRIT_TOPIC:gerrit_topic,
        GERRIT_EVENT_TYPE:build.environment.get("GERRIT_EVENT_TYPE", ""))

    if (build.environment.get("TEST_ONE_DEVICE", "false") == "true") {
        build(job_name_repo_reference,
            DEVICE_NAME:"hammerhead",
            MANIFEST_URL:manifest_url,
            MANIFEST_BRANCH:manifest_branch,
            PIPELINE_NUMBER:build.number,
            DIST_NAME:dist_name)
    } else {
        parallel (
        {
          build(job_name_repo_reference,
                DEVICE_NAME:"hammerhead",
                MANIFEST_URL:manifest_url,
                MANIFEST_BRANCH:manifest_branch,
                PIPELINE_NUMBER:build.number,
                DIST_NAME:dist_name)
        },
        {
          build(job_name_repo_reference,
                DEVICE_NAME:"flo",
                MANIFEST_URL:manifest_url,
                MANIFEST_BRANCH:manifest_branch,
                PIPELINE_NUMBER:build.number,
                DIST_NAME:dist_name)
        },
        {
          build(job_name_repo_reference,
                DEVICE_NAME:"mako",
                MANIFEST_URL:manifest_url,
                MANIFEST_BRANCH:manifest_branch,
                PIPELINE_NUMBER:build.number,
                DIST_NAME:dist_name)
        }
        )
    }
}
