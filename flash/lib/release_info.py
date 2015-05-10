import json

class ReleaseInfo(object):
    @classmethod
    def from_file(cls, file_name):
        file_h = open(file_name, 'r')
        data_array = json.load(file_h)
        file_h.close()
        return cls.from_array(data_array)

    @classmethod
    def from_array(cls, attributes):
        """
        Returns an instance of ReleaseInfo using cm.updater.uri attributes.

        For example: {
            u'url': u'http://get.cm/get/jenkins/67680/cm-11-20140504-SNAPSHOT-M6-hammerhead.zip',
            u'timestamp': u'1399238905',
            u'md5sum': u'99f94c0f21195e52830ad34062cdc303',
            u'filename': u'cm-11-20140504-SNAPSHOT-M6-hammerhead.zip',
            u'incremental': u'e45bcd7e97',
            u'api_level': 19,
            u'changes': u'http://get.cm/get/jenkins/67680/CHANGES.txt',
            u'channel': u'snapshot'}
        """
        cm_zip = cls()
        cm_zip.url = attributes['url']
        cm_zip.timestamp = attributes['timestamp']
        cm_zip.md5sum = attributes['md5sum']
        cm_zip.filename = attributes['filename']
        cm_zip.incremental = attributes['incremental']
        cm_zip.api_level = attributes['api_level']
        cm_zip.changes = attributes['changes']
        cm_zip.channel = attributes['channel']

        # re-serialize the attributes so it can be cached
        cm_zip.raw = json.dumps(attributes)

        return cm_zip

    def __str__(self):
        return "ReleaseInfo { url: '%s', incremental: '%s', channel: '%s' }" % \
            (self.url, self.incremental, self.channel)
