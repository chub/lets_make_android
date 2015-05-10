from .exceptions import NoBuildsFoundException
from .single_apk_build import SingleApkBuild
from .sideloadable_ota_build import SideloadableOtaBuild

class BuildSet(object):
    """
    Locates the appropriate sideloadable zip / FOTA / APK combination for the
    situation.

    1. Check if pipeline is an APK build
    2. Check if pipeline is an cm-11.0-based delta OTA
    3. Check if pipeline is a cm-12.0 FOTA
    """
    TYPE_UNKNOWN = "UNKNOWN"
    TYPE_APK_ONLY = "APK_ONLY"
    TYPE_DELTA_OTA = "DELTA_OTA"
    TYPE_FULL_OTA = "FULL_OTA"

    def __init__(self,
                 device=None,
                 dist=None,
                 pipeline_number=None):
        if device is None:
            raise Exception('Invalid device value of None')
        self.device = device

        self.dist = dist
        self.pipeline_number = pipeline_number

        self.type = self.TYPE_UNKNOWN
        # APK vs OTA builds
        self.apk_build = None
        self.ota_build = None

        # Search for delta OTA or full OTA
        # Should match cm-11.0 and cm-12.0 builds
        if self.type == self.TYPE_UNKNOWN:
            try:
                build = SideloadableOtaBuild(
                    device=self.device,
                    dist=self.dist,
                    pipeline_number=self.pipeline_number)
                build.find_s3_path()
                if build.is_delta_ota():
                    self.type = self.TYPE_DELTA_OTA
                else:
                    self.type = self.TYPE_FULL_OTA
                self.ota_build = build
            except NoBuildsFoundException:
                pass

        # Search for APK if this isn't a DELTA_OTA.
        if self.type != self.TYPE_DELTA_OTA:
            apk_dist = self.dist
            try:
                self.apk_build = SingleApkBuild(
                    dist=apk_dist,
                    pipeline_number=self.pipeline_number,
                    artifact='sdk_app-debug.apk')
            except NoBuildsFoundException:
                self.apk_build = None

if __name__ == '__main__':
    device = 'hammerhead'
    pipeline_number = None
    dist = 'cm-12.1'

    build_set = BuildSet(device=device,
                         dist=dist,
                         pipeline_number=pipeline_number)
    print "build_set Type: %s" % build_set.type
    print "ota_build: %r" % build_set.ota_build
    print "  " + build_set.ota_build.get_local_path()
    print "  " + build_set.ota_build.get_base_cm_filename()
    print "apk_build: %r" % build_set.apk_build
    print "  " + build_set.apk_build.get_local_path()
