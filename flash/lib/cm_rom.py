#! /usr/bin/python

import argparse
import os
import sys
import traceback
from zipfile import ZipFile

from .get_cm import GetCm
from .download_client import DownloadClient
from .release_info import ReleaseInfo

class CmRom(object):
    """
    This represents open-source CyanogenMod builds (SNAPSHOT, MILESTONE, RC, STABLE).
    """
    BUILD_PROP_LOCATION = 'system/build.prop'
    BUILD_MANIFEST_LOCATION = 'system/etc/build-manifest.xml'

    def __init__(self, device_name,
                 cache_dir=None,
                 stay_offline=False,
                 download_client=None,
                 cm_version=None,
                 cm_milestone=None,
                 cm_filename=None):
        """
        - download_client is used on cache misses and saves downloaded zips.
        - cm_* parameters are sent to GetCm()
        """
        self.device_name = device_name

        if cache_dir is None:
            cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'blobs', 'release_cache'))
        self.cache_dir = cache_dir

        if download_client is None:
            download_client = DownloadClient()
        self.download_client = download_client

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        elif not os.path.isdir(self.cache_dir):
            raise Exception('CmRom: "%s" is not a directory' % self.cache_dir)

        self.cm_zip_info = None
        if not stay_offline:
            try:
                get_cm = GetCm(version=cm_version, milestone=cm_milestone, filename=cm_filename)
            except:
                traceback.print_exc()
                print 'Unable to read from get.cm'
                print 'Will use last-used data for device "%s"' % self.device_name

            self.cm_zip_info = get_cm.get_cm_zip_info(self.device_name)
            self._update_release_cache()

        if self.cm_zip_info is None:
            # Reached here either because stay_offline was true, or because GetCm threw exception
            cached_info_file = os.path.join(self._get_cached_release_path(), 'device.json')

            if not os.path.exists(cached_info_file):
                raise Exception('No offline data available for device "%s"' % self.device_name)

            self.cm_zip_info = ReleaseInfo.from_file(cached_info_file)

    def _update_release_cache(self):
        target_path = self._get_target_release_path()

        if not os.path.exists(target_path):
            os.makedirs(target_path)

        # Create or truncate device.json
        file_h = open(os.path.join(target_path, 'device.json'), 'w+')
        file_h.write(self.cm_zip_info.raw)
        file_h.close()

        # Update the symlink
        symlink_path = self._get_cached_release_path()
        if os.path.exists(symlink_path):
            if os.path.islink(symlink_path) or os.path.isfile(symlink_path):
                os.unlink(symlink_path)
            else:
                print >> sys.stderr, 'Unable to update cache. Expected symlink here %s' % symlink_path
                return False

        # e.g.: hammerhead-latest should point to hammerhead-e45bcd7e97
        # instead of: /RELEASE_CACHE_PATH/release_cache/hammerhead-e45bcd7e97
        os.symlink(self._get_target_release_basename(), symlink_path)
        return True

    def _get_target_release_basename(self):
        """
        Returns a unique directory name representing a device and release.

        e.g. 'hammerhead-e45bcd7e97'
        """
        return '%s-%s' % (self.device_name, self.cm_zip_info.incremental)

    def _get_target_release_path(self):
        """
        Returns a directory where cached files live

        e.g. build.prop, build-manifest.xml, device.json
        """
        return os.path.join(self.cache_dir, self._get_target_release_basename())

    def _get_cached_release_path(self):
        return os.path.join(self.cache_dir, '%s-latest' % self.device_name)

    def _get_file_from_zip(self, compressed_file):
        """
        compressed_file: Path to the file inside the zipfile, e.g. "/system/build.prop"
        """
        target_dir = self._get_target_release_path()

        # Check whether we have uncompressed this file before.
        uncompressed_file = os.path.join(target_dir, compressed_file)
        if os.path.exists(uncompressed_file):
            return uncompressed_file

        # If not, download the release and extract it.
        if self.download_client:
            zipfile = self.download_client.get_local_path(self.cm_zip_info.url,
                                                          md5sum=self.cm_zip_info.md5sum)
            print >> sys.stderr, 'Extracting %s from %s' % (compressed_file, zipfile)
            with ZipFile(zipfile, 'r') as zipfile_h:
                zipfile_h.extract(compressed_file, target_dir)
            return uncompressed_file

        # No cache, and cannot download from get.cm.
        raise Exception('%s for %s not found' % (compressed_file, self.device_name))

    def get_build_prop(self):
        return self._get_file_from_zip(self.BUILD_PROP_LOCATION)

    def get_build_manifest(self):
        return self._get_file_from_zip(self.BUILD_MANIFEST_LOCATION)

    def get_zip(self):
        return self.download_client.get_local_path(self.cm_zip_info.url,
                                                   md5sum=self.cm_zip_info.md5sum)

if __name__ == '__main__':
    def argparse_dir(path):
        if not os.path.isdir(path):
            raise argparse.ArgumentTypeError('%s is not a directory: %s' % path)
        return path

    def get_flags():
        parser = argparse.ArgumentParser()
        parser.add_argument('--download_cache',
                            type=argparse_dir,
                            help='directory where downloads are cache')
        parser.add_argument('--release_cache',
                            type=argparse_dir,
                            help='directory where releases are cached')
        parser.add_argument('--device_name', required=True, type=str,
                            help='selected Android device')
        parser.add_argument('--cm_milestone', type=str,
                            help='specify a CM snapshot milestone')
        parser.add_argument('--cm_version', type=str,
                            help='specify a CM version')
        parser.add_argument('--cm_filename', type=str,
                            help='specify a CM filename')
        parser.add_argument('--stay_offline', action='store_true',
                            help='avoids calling get.cm')
        parser.add_argument('--show_build_prop', action='store_true',
                            help='display path to build.prop')
        parser.add_argument('--show_build_manifest', action='store_true',
                            help='display path to build-manifest.xml')
        return parser.parse_args()

    flags = get_flags()

    download_client = None
    if flags.download_cache:
        download_client = DownloadClient(flags.download_cache)

    cm_rom = CmRom(flags.device_name,
                   cache_dir=flags.release_cache,
                   download_client=download_client,
                   stay_offline=flags.stay_offline,
                   cm_version=flags.cm_version,
                   cm_milestone=flags.cm_milestone,
                   cm_filename=flags.cm_filename)
    if flags.show_build_prop:
        print cm_rom.get_build_prop()
    if flags.show_build_manifest:
        print cm_rom.get_build_manifest()
