import os
import subprocess
from zipfile import ZipFile

from download_client import DownloadClient

class ApkS3RootNotImplementedError(NotImplementedError): pass

class SingleApkBuild(object):
    """
    This represents a single APK.
    """

    def __init__(self, download_client=None, dist=None, build_number=None,
                 pipeline_number=None, artifact=None):
        if download_client is None:
            download_client = DownloadClient()
        self.download_client = download_client

        if dist is None:
            # If dist was not provided, assume master.
            dist = 'master'
        self.dist = dist

        self.build_number = build_number
        self.pipeline_number = pipeline_number
        self.artifact = artifact

        # Memoized fields
        self.s3_path = None
        self.local_path = None

    def find_s3_root(self):
        raise ApkS3RootNotImplementedError()

    def find_s3_path(self):
        """
        Constructs and searches for the S3 path to the APK build, e.g.:

        s3://BUCKET/files/clients/CLIENT_NAME/BRANCH/B677--2014-08-21_18-16-49/apk/sdk_app-debug.apk
        """
        if self.s3_path is not None:
            return self.s3_path

        s3_list_cmd = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'list_builds_client.sh')),
            '--dist=%s' % self.dist,
            '--numrows=1',
            '--artifact=%s' % self.artifact,
            ]
        if self.build_number is not None:
            s3_list_cmd.append('--build_number=%d' % self.build_number)
        if self.pipeline_number is not None:
            s3_list_cmd.append('--pipeline_number=%d' % self.pipeline_number)

        s3_list = subprocess.Popen(s3_list_cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        output, errout = s3_list.communicate()
        if s3_list.returncode != 0:
            raise Exception('Unable to query list_builds_client.sh: %s' % errout)

        builds = output.splitlines()
        if len(builds) == 1:
            self.s3_path = builds[0]
            return self.s3_path
        elif len(builds) > 1:
            raise Exception('Multiple APK builds (%d) found for %r' % (len(builds), self.__dict__))
        else:
            raise Exception('No APK builds found for %r' % self.__dict__)

    def get_local_path(self):
        """
        Returns a filepath to the downloaded APK build, e.g.:

        /DOWNLOAD_CACHE_ROOT/download_cache/ad8e8d80466c7e4cbd357c3c86e491210a9ff2ee/sdk_app-release.apk
        """
        if self.local_path is not None:
            return self.local_path

        s3_path = self.find_s3_path()
        self.local_path = self.download_client.get_local_path(s3_path)
        return self.local_path

if __name__ == '__main__':
    build_number = None
    pipeline_number = None
    dist = 'cm-g'
    artifact = 'sdk_app-debug.apk'

    single_apk_build = SingleApkBuild(dist=dist,
                                      build_number=build_number,
                                      pipeline_number=pipeline_number,
                                      artifact=artifact)
    print 's3 path: %s' % single_apk_build.find_s3_path()
    print 'local path: %s' % single_apk_build.get_local_path()
