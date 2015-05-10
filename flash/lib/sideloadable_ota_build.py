import os
import subprocess
from zipfile import ZipFile

from .build_prop_common import BuildPropCommon
from .download_client import DownloadClient
from .exceptions import NoBuildsFoundException, ManyBuildsFoundException
from .s3cmd_locator import S3CmdLocator

class SideloadableOtaBuild(object):
    """
    Represents one delta OTA (APKs all associated framework changes), or a full OTA (cm-12-*.zip).
    """
    # Delta OTAs are always stored in this static path.
    DELTA_OTA_ZIP_FILE = 'ota/delta.zip'

    BUILD_PROP_LOCATION = 'system/build.prop'
    CM_BASE_PROP_1 = 'ro.cm.display.version'
    CM_BASE_PROP_2 = 'ro.modversion'

    def __init__(self, download_client=None, device=None, dist=None, pipeline_number=None):
        if download_client is None:
            download_client = DownloadClient()
        self.download_client = download_client

        if device is None:
            raise Exception('Invalid device value of None')
        self.device = device

        self.dist = dist

        self.pipeline_number = pipeline_number

        # Memoized fields
        self.s3_root = None
        self.s3_path = None
        self.local_path = None
        self.cached_build_prop_common = None
        self.base_cm_filename = None

    def find_s3_root(self):
        """
        Constructs and searches for the S3 root to the sideloadable build, e.g.:

        s3://BUCKET/files/devices/BRANCH/hammerhead/B448-P100--2014-06-07_03-07-56--jenkins-job/
        """
        if self.s3_root is not None:
            return self.s3_root

        s3_list_cmd = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'list_builds.sh')),
            '--device=%s' % self.device,
            '--dist=%s' % self.dist,
            '--numrows=1'
            ]
        if self.pipeline_number is not None:
            s3_list_cmd.append('--pipeline_number=%d' % self.pipeline_number)

        s3_list = subprocess.Popen(s3_list_cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        output, errout = s3_list.communicate()
        if s3_list.returncode != 0:
            raise Exception('Unable to query list_builds.sh: {}'.format(errout))

        builds = output.splitlines()
        if len(builds) == 1:
            self.s3_root = builds[0]
            return self.s3_root
        elif len(builds) > 1:
            raise ManyBuildsFoundException('Multiple delta OTA builds (%d) found %r, %r' % (len(builds), self.__dict__, output))
        else:
            raise NoBuildsFoundException('No delta OTA builds found for %r' % self.__dict__)

    def find_s3_path_fota(self):
        """
        Constructs and searches for the S3 path to the FOTA, e.g.:

        s3://BUCKET/files/devices/BRANCH/flo/B45-P1918--2015-02-06_22-45-27--jenkins/rom/cm-12-20150206-UNOFFICIAL-P1918-flo.zip
        """
        if self.s3_path is not None:
            return self.s3_path

        s3_list_cmd = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'list_builds_client.sh')),
            '--artifact=fota',
            '--device=%s' % self.device,
            '--dist=%s' % self.dist,
            '--numrows=1'
            ]
        if self.pipeline_number is not None:
            s3_list_cmd.append('--pipeline_number=%d' % self.pipeline_number)

        s3_list = subprocess.Popen(s3_list_cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        output, errout = s3_list.communicate()
        if s3_list.returncode != 0:
            raise Exception('Unable to query list_builds_client.sh: {}'.format(errout))

        builds = output.splitlines()
        if len(builds) == 1:
            self.s3_path = builds[0]
            return self.s3_root
        elif len(builds) > 1:
            raise ManyBuildsFoundException('Multiple FOTA builds (%d) found for %r, %r' % (len(builds), self.__dict__, output))
        else:
            raise NoBuildsFoundException('No FOTA builds found for %r' % self.__dict__)

    def is_delta_ota(self):
        # Distributions that were structured as delta OTAs
        if self.dist.endswith('-cm-11.0') or \
           self.dist.startswith('cm-a') or \
           self.dist.startswith('cm-b') or \
           self.dist.startswith('cm-c') or \
           self.dist.startswith('cm-d') or \
           self.dist.startswith('cm-e') or \
           self.dist.startswith('cm-f') or \
           self.dist.startswith('cm-g'):
            return True
        return False

    def find_s3_path(self):
        """
        Constructs the S3 path to the sideloadable build.

        Different builds have different flashable items.
        - For delta OTAs, the flashable item is always located at DELTA_OTA_ZIP_FILE.
        - For full OTAs, the filenames are unique and must be found.

        s3://BUCKET/files/devices/BRANCH/hammerhead/B448-P100--2014-06-07_03-07-56--jenkins-job/ota/delta.zip
        """
        # Distributions that were structured as delta OTAs
        if self.is_delta_ota():
            return '%s%s' % (self.find_s3_root(), self.DELTA_OTA_ZIP_FILE)
        else:
            return self.find_s3_path_fota()

    def get_local_path(self):
        """
        Returns a filepath to the downloaded sideloadable OTA build, e.g.:

        /DOWNLOAD_CACHE_ROOT/4ec38df749d7f563e0361040eafb3e1d451e4036/delta.zip
        """
        if self.local_path is not None:
            return self.local_path

        s3_path = self.find_s3_path()
        self.local_path = self.download_client.get_local_path(self.find_s3_path())
        return self.local_path

    def get_build_prop_common(self):
        """
        Returns a cached copy of BuildPropCommon, which actually unzips a zip and parses
        build.prop files.
        """
        if self.cached_build_prop_common is None:
            self.cached_build_prop_common = BuildPropCommon(self.get_local_path())
        return self.cached_build_prop_common


    def getprop_system(self, prop=None):
        return self.get_build_prop_common().get_prop(prop=prop)

    def get_base_cm_filename(self):
        """
        Returns the CM build needed to install this sideloadable ZIP.
        """
        return self.get_build_prop_common().get_base_cm_filename()

    def get_aosp_version(self):
        """
        Returns the AOSP major.minor in this OTA.
        """
        return self.get_build_prop_common().get_aosp_version()

if __name__ == '__main__':
    device = 'hammerhead'
    dist = 'cm-12.1'
    pipeline_number = None

    ota_build = SideloadableOtaBuild(device=device,
                                     dist=dist,
                                     pipeline_number=pipeline_number)
    print 's3 root: %s' % ota_build.find_s3_root()
    print 's3 path: %s' % ota_build.find_s3_path()
    print 'local path: %s' % ota_build.get_local_path()
    print 'cm base: %s' % ota_build.get_base_cm_filename()
