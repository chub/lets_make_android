#! /usr/bin/python

import json
import re
import sys
import urllib

from .release_info import ReleaseInfo

class GetCm(object):
    # Sample of filenames
    # cm-11-20140608-SNAPSHOT-M7-crespo.zip
    # cm-11-20140609-SNAPSHOT-M7-flo.zip
    # cm-11-20140504-SNAPSHOT-M6-hammerhead.zip
    # cm-11-20140405-SNAPSHOT-M5-hammerhead.zip
    # cm-10.2.0-RC1-crespo.zip
    FILENAME_PARSER = re.compile('cm-([^-]+)-[0-9]{8}-SNAPSHOT-M([0-9]+)-([^.]+).zip')

    # Sample of ro.modversions
    # 11-20141121-SNAPSHOT-M12-hammerhead
    MODVERSION_PARSER = re.compile('^([^-]+)-[0-9]{8}-SNAPSHOT-M([0-9]+)-([^.]+)')

    def __init__(self,
                 version=None,
                 milestone=None,
                 filename=None,
                 updater_url=None):
        """
        Arguments
        - updater_url should be set to the value of cm.updater.uri
        - version should be the CM version (10, 10.1, 11)
        - milestone should be the milestone number (5, 6, 7, 8, etc)
        - filename filters the returned filenames. should not be used with either version or milestone
        """
        # Check that version/milestone are mutually exclusive from filename
        if (version is not None or milestone is not None) and (filename is not None):
            raise Exception('filename(%s) should not be used with version(%s) or milestone(%s)' % (
                filename, version, milestone))

        self.version = version
        self.milestone = milestone
        self.filename = filename
        self.updater_url = updater_url or \
            'http://beta.download.cyanogenmod.org/api'

        # Populate version and milestone if not passed as arguments and if modversion can be parsed
        # (Though the argument is called filename, the value is sometimes populated by the
        # modversion from a build.prop file)
        if filename is not None and \
           (self.version is None or self.milestone is None):
            parsed = self.parse_modversion(filename=self.filename)

            if parsed[0] is not None and self.version is None:
                self.version = parsed[0]
                print >> sys.stderr, "Infer version %s from filename %s" % (self.version, filename)

            if parsed[1] is not None and self.milestone is None:
                self.milestone = parsed[1]
                print >> sys.stderr, "Infer milestone %s from filename %s" % (self.milestone, filename)

    @classmethod
    def parse_modversion(cls, filename=None):
        """
        Returns a tuple of all the parsed groups.  Values may be None.
        """
        parsed_version = None
        parsed_milestone = None
        parsed_device_name = None

        if filename is not None:
            parsed = cls.MODVERSION_PARSER.search(filename)
            if parsed:
                parsed_version = parsed.group(1)
                parsed_milestone = parsed.group(2)
                parsed_device_name = parsed.group(3)

        return (parsed_version, parsed_milestone, parsed_device_name)

    def release_matches(self, device_name=None, release=None):
        # Skip verification
        if device_name is None and self.version is None and self.milestone is None and self.filename is None:
            return True

        if 'filename' not in release:
            return False

        # Match by filename
        if self.filename is not None:
            # Perform search for --cm_filename=11-20140608-M7-crespo
            return self.filename in release['filename']
        # Match with device/version/milestone
        else:
            parsed = self.FILENAME_PARSER.search(release['filename'])
            if not parsed:
                return False

            # verify each item in serial
            if self.version is not None and \
               self.version != parsed.group(1):
                return False

            if self.milestone is not None and \
               self.milestone != parsed.group(2):
                return False

            if device_name is not None and \
               device_name != parsed.group(3):
                return False

            return True

    def is_getting_latest(self):
        return self.version is None and self.milestone is None and self.filename is None

    def get_release_info_for_bacon_cm_11_m10_nightly_20140915(self):
        return ReleaseInfo.from_array(json.loads("""
          {
           "url": "http://get.cm/get/jenkins/83639/cm-11-20140915-NIGHTLY-bacon.zip",
           "timestamp": "1410770310",
           "md5sum": "680c36abde156d3f73daf7ae8266315a",
           "filename": "cm-11-20140915-NIGHTLY-bacon.zip",
           "incremental": "1ef7c8d38d",
           "channel": "nightly",
           "changes": "http://get.cm/get/jenkins/83639/CHANGES.txt",
           "api_level": 19
          }
        """))

    def get_release_info_for_bacon_cm_11_m10_nightly_20140917(self):
        return ReleaseInfo.from_array(json.loads("""
          {
           "url": "http://get.cm/get/jenkins/83809/cm-11-20140917-NIGHTLY-bacon.zip",
           "timestamp": "1410914607",
           "md5sum": "c3fc2ce392c309d843debb3b937dd167",
           "filename": "cm-11-20140917-NIGHTLY-bacon.zip",
           "incremental": "b9ff5eaca1",
           "channel": "nightly",
           "changes": "http://get.cm/get/jenkins/83809/CHANGES.txt",
           "api_level": 19
          }
        """))

    def get_cm_zip_info(self, device_name):
        """
        Query for the latest channels=snapshot for the device.
        """
        response_str = None
        # Check for hijack
        if device_name == 'bacon' and self.version == '11' and self.milestone == '10':
            print >> sys.stderr, 'Skipping CyanogenMod build servers for query: %s cm-%s M%s' % (device_name, self.version, self.milestone)
            return self.get_release_info_for_bacon_cm_11_m10_nightly_20140915()

        # Execute RPC Query under normal circumstances
        post_payload = {
            'method': 'get_all_builds',
            'params': {
                # Channels can also contain 'release', 'RC', and 'nightly'
                'channels': ['snapshot'],
                'device' : device_name,
            }}
        if self.is_getting_latest():
            # Request the latest one
            post_payload['params']['limit'] = 1

        print >> sys.stderr, 'Querying CyanogenMod build servers for %s builds...' % device_name
        request = urllib.urlopen(self.updater_url, json.dumps(post_payload))
        response_str = request.read()
        print >> sys.stderr, 'Reading response from CyanogenMod build servers for %s builds...' % device_name

        response_obj = json.loads(response_str)
        if 'result' in response_obj:
            release_list = response_obj['result']
            # In case limit > 1, sort by 'timestamp' descending
            if len(release_list) > 0:
                release_list = sorted(release_list,
                                      key=lambda release: release['timestamp'],
                                      reverse=True)
                for release in release_list:
                    if self.release_matches(device_name=device_name, release=release):
                        print >> sys.stderr, "Returning: %r" % (release)
                        return ReleaseInfo.from_array(release)

        # Should have returned by now
        if self.is_getting_latest():
            raise Exception('Unable to find latest snapshot for device "%s"' % device_name)
        else:
            raise Exception('Unable to find snapshot (version=%s, milestone=%s) for device "%s"' % (
                self.version,
                self.milestone,
                device_name))
