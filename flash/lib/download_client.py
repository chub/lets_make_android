#! /usr/bin/python

import hashlib
import os
import subprocess
import sys

from urllib2 import urlparse

from .colorcli import ColorCli
from .s3cmd_locator import S3CmdLocator
from mercurial import (
    lock,
    error as mercurial_error,
)

def hashfile(filename, hash_type=hashlib.md5):
    hasher = hash_type()
    with open(filename, 'rb') as file_h:
        for chunk in iter(lambda: file_h.read(128 * hasher.block_size), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

class DownloadClient(object):
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'blobs', 'download_cache'))
        self.cache_dir = cache_dir
        self.create_cache_dir()

    def create_cache_dir(self):
        if os.path.exists(self.cache_dir):
            if not os.path.isdir(self.cache_dir):
                raise Exception('cache_dir "%s" is not a directory' % self.cache_dir)
        else:
            os.makedirs(self.cache_dir, mode=0755)

    def _get_target_dir(self, url):
        """
        Directory in which cached files for URL live.
        """
        hashed_url = hashlib.sha1(url).hexdigest()
        return os.path.join(self.cache_dir, hashed_url)

    @classmethod
    def get_url_basename(cls, url):
        """
        Returns the basename of the path described in the URL.

        For example:
        http://www.google.com/search?q=blahbla => "search"
        http://get.cm/get/jenkins/67680/cm-11-20140504-SNAPSHOT-M6-hammerhead.zip => cm-11-20140504-SNAPSHOT-M6-hammerhead.zip
        """
        try:
            return os.path.basename(urlparse.urlparse(url).path)
        except:
            return 'cached_file'

    def get_cached_path(self, url):
        local_dir = self._get_target_dir(url)

        verified_source_url = False
        verified_md5sum_file = False

        # Read the cached source_url, if it exists
        source_url_filepath = os.path.join(local_dir, 'source_url')
        if os.path.exists(source_url_filepath):
            source_url_handle = open(source_url_filepath, 'r')
            cached_source_url = source_url_handle.read()
            source_url_handle.close()
            if cached_source_url == url:
                verified_source_url = True

        # Read cached md5sum, if it exists
        md5sum = None
        md5sum_filepath = os.path.join(local_dir, 'md5sum')
        if os.path.exists(md5sum_filepath):
            md5sum_handle = open(md5sum_filepath, 'r')
            md5sum_line = md5sum_handle.read()
            # Assume md5sum is the first element of the file
            if md5sum_line:
                md5sum_parts = md5sum_line.split()
                if len(md5sum_parts) > 0:
                    md5sum = md5sum_parts[0]

        basename = self.get_url_basename(url)
        cached_path = os.path.join(local_dir, basename)

        if os.path.exists(cached_path):
            if md5sum is not None:
                print >> sys.stderr, 'Verifying cached %s with MD5 (%s)' % (basename, md5sum)
                actual_md5sum = hashfile(cached_path)
                if md5sum != actual_md5sum:
                    print >> sys.stderr, 'Expected md5 %s, actual md5 is %s; please redownload' % (md5sum, actual_md5sum)
                    return None
                else:
                    verified_md5sum_file = True

        if os.path.exists(cached_path) and (verified_source_url or verified_md5sum_file):
            return cached_path

        # Cache does not exist.
        return None

    def get_local_path(self, url, md5sum=None, trusted_md5sum=None):
        """
        Returns a local path of the URL contents.

        If cached locally (in cache_dir), immediately returns the path.
        Otherwise, downloads the file, saves it to the cache, and returns the path.

        Arguments:
        - md5sum: if set, new downloads must match the indicated md5sum (old downloads do not)
        - trusted_md5sum: if set, this overrides the md5sum argument, and all existing and downloads must match the indicated md5sum
        """
        path_to_cached_download = self.get_cached_path(url)
        if path_to_cached_download:
            return path_to_cached_download

        # This is the cache prefix, e.g. "/DOWNLOAD_CACHE_ROOT/download_cache/320ef6acf360e72cbc54ad58e4d7c8d046de4d46"
        cache_prefix = self._get_target_dir(url)
        if not os.path.isdir(cache_prefix):
            os.makedirs(cache_prefix)

        # Path to lock on
        lock_path = os.path.join(cache_prefix, 'lock')

        # Provide feedback if there is another download in progress
        there_is_another_lock = False

        # mercurial lock creates a symlink at lock_path.  However, we check both (just in case).
        if os.path.lexists(lock_path) or os.path.exists(lock_path):
            there_is_another_lock = True
            print >> sys.stderr, 'Will stop to wait for url: %s' % url
            ColorCli.print_red('Another download is in progress.  Will wait up to 600 seconds. Ctrl-C to stop any time.')

        try:
            # Grab lock for 10 minutes
            l = lock.lock(lock_path, timeout=600)
            l.lock()

            if there_is_another_lock:
                ColorCli.print_green('Done waiting for other download.')

            # Call the inner method that is protected by a lock
            return self._get_local_path_singleton(url, md5sum=md5sum, trusted_md5sum=trusted_md5sum)
        except mercurial_error.LockHeld:
            # couldn't take the lock
            ColorCli.print_red('Timed out waiting for the lock.  Exiting.')
            sys.exit(1)
        else:
            l.release()

    def _get_local_path_singleton(self, url, md5sum=None, trusted_md5sum=None):
        # This is the cache prefix, e.g. "/DOWNLOAD_CACHE_ROOT/download_cache/320ef6acf360e72cbc54ad58e4d7c8d046de4d46"
        cache_prefix = self._get_target_dir(url)
        if not os.path.isdir(cache_prefix):
            os.makedirs(cache_prefix)

        # Extract basename from url, e.g. "file.zip" from "(s3|https)://SOME_URL/blah/blah/file.zip"
        basename = self.get_url_basename(url)

        target_filepath = os.path.join(cache_prefix, basename)
        md5sum_filepath = os.path.join(cache_prefix, 'md5sum')

        # Perform trusted_md5sum operations
        # This variable is significant when another source is authoritative about our downloads (get.cm, for example)
        if trusted_md5sum is not None:
            if os.path.exists(md5sum_filepath):
                md5sum = self.get_md5sum_for_url(url, md5sum_filepath=md5sum_filepath)

            # Notify user that an override is happening
            if md5sum is not None and md5sum != trusted_md5sum:
                print >> sys.stderr, 'Overriding original md5sum (%s) with trusted_md5sum (%s)' % (md5sum, trusted_md5sum)

            # Save the trusted md5sum
            trusted_md5sum_h = open(md5sum_filepath, 'w+')
            trusted_md5sum_h.write('%s\ttrusted_md5sum\n' % trusted_md5sum)
            trusted_md5sum_h.close()

            # Replace the md5sum, in case it was set
            md5sum = trusted_md5sum

        # Get md5sum from URL if it was not specified
        # TODO, we could save the md5sum argument if it matches our download
        if md5sum is None:
            md5sum = self.get_md5sum_for_url(url, md5sum_filepath=md5sum_filepath)

        valid_target_filepath = False
        fetched = False

        # Backwards-compatibility
        if os.path.exists(target_filepath):
            # Sometimes the cache_dir has no source_url file but the download is there.
            # 1. If the md5sum is known, verify the md5sum file.
            # 1.5. If the md5sum does not match, then ditch the existing file and start over.
            if md5sum is not None:
                actual_md5sum = hashfile(target_filepath)
                if actual_md5sum == md5sum:
                    valid_target_filepath = True
                else:
                    print >> sys.stderr, "Last download was corrupt. expected md5 %s, actual_md5 %s" % (md5sum, actual_md5sum)
                    print >> sys.stderr, "Deleting %s" % target_filepath
                    os.unlink(target_filepath)
            # 2. If the md5sum is not known, ditch it and download it again (backwards-compatible behavior).
            else:
                valid_target_filepath = False

        if not valid_target_filepath:
            print >> sys.stderr, 'Downloading URL "%s" into "%s"' % (url, target_filepath)
            fetched = self.fetch_url(url, target_filepath)

        if fetched:
            # Verify checksum
            if md5sum is not None:
                actual_md5sum = hashfile(target_filepath)
                if actual_md5sum != md5sum:
                    raise Exception('Expected hash %s, actual hash %s. URL: %s' % (
                        md5sum, actual_md5sum, url))
                else:
                    valid_target_filepath = True

        # Wrap it up.
        if valid_target_filepath or fetched:
            # Save the source_url
            source_url_handle = open(os.path.join(cache_prefix, 'source_url'), 'w')
            source_url_handle.write(url)
            source_url_handle.close()

            return target_filepath
        else:
            raise Exception('Unable to download URL "%s"' % url)

    def get_md5sum_for_url(self, url, md5sum_filepath=None):
        """
        Returns the md5sum for the URL.  None if the md5sum is not known.

        This method also caches its result in the 'md5sum' file.
        """
        if md5sum_filepath is None:
            # By default, download_cache/BLAHchecksumBLAH/md5sum
            md5sum_filepath = os.path.join(self._get_target_dir(url), 'md5sum')

        # If the md5sum file is not cached, try to download it
        if not os.path.exists(md5sum_filepath):
            if url.startswith("s3://"):
                # Assume the location is '.md5sum' suffix
                self.fetch_url(url + '.md5sum', md5sum_filepath)
            else:
                print >> sys.stderr, 'URL for md5sum of "%s" is unknown.' % url

        # Try to read the md5sum file
        md5sum = None
        if os.path.exists(md5sum_filepath):
            md5sum_h = open(md5sum_filepath, 'r')
            md5sum_contents = md5sum_h.read()
            md5sum_h.close()

            if md5sum_contents:
                md5sum_parts = md5sum_contents.split()
                if len(md5sum_parts) > 0:
                    md5sum = md5sum_parts[0]

        return md5sum

    def fetch_url(self, url, target_filepath):
        # Save download to tmp file
        tmp_target_filepath = target_filepath + '.tmp'

        # Return if the fetch was successful.
        fetched = False

        if url.startswith("s3://"):
            s3cmd = [S3CmdLocator.get_path(), 'get', url, tmp_target_filepath]
            if os.path.exists(tmp_target_filepath):
                print >> sys.stderr, 'Resuming last download to %s' % tmp_target_filepath
                s3cmd.insert(2, '--continue')
            s3cmd_rv = subprocess.call(s3cmd)
            fetched = s3cmd_rv == 0
        else:
            # Assume curl
            if os.path.exists(tmp_target_filepath):
                print >> sys.stderr, 'Removing last temp file at %s' % tmp_target_filepath
                os.unlink(tmp_target_filepath)
            curl_cmd_rv = subprocess.call(['curl', '-#', '-L', '-o', tmp_target_filepath, url])
            fetched = curl_cmd_rv == 0

        if os.path.exists(tmp_target_filepath):
            if fetched:
                # Remove .tmp suffix if successful
                os.rename(tmp_target_filepath, target_filepath)
            else:
                # Delete tmp file if the operation failed
                os.unlink(tmp_target_filepath)

        return fetched

if __name__ == '__main__':
    dc = DownloadClient('/tmp/workspace/download_cache')
    #c_p = dc.get_local_path('http://get.cm/get/jenkins/67680/cm-11-20140504-SNAPSHOT-M6-hammerhead.zip')
    #print c_p

    gapps_url = 'https://raw.githubusercontent.com/chub/lma_blobs/firmware/gapps/pa_gapps-stock-4.4.4-20141119-signed-keeptmp.zip'
    gapps_md5sum = dc.get_md5sum_for_url(gapps_url)
    print "md5sum is:"
    print gapps_md5sum
    #gapps_path = dc.get_local_path(gapps_url)
    #print "path is: "
    #print gapps_path
    gapps_path = dc.get_local_path(gapps_url, md5sum='c955e7a6f4f39810552d216958b900db')
    print "path is: "
    print gapps_path
    #gapps_path = dc.get_local_path(gapps_url, trusted_md5sum='c955e7a6f4f39810552d216958b900db')
    #print "path is: "
    #print gapps_path
