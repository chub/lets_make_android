import sys
import urllib

from bs4 import BeautifulSoup

from .blobs_cache import BlobsCache

class Recovery(BlobsCache):
    # Pins an image name for stability (and is saved in S3 bucket).
    # If a device is not defined here, the class will fall back to the latest TWRP image.
    DEVICE_TO_IMAGE_NAME = {
        # DO NOT USE TWRP 2.8.6.0 for bacon. recovery is reported as 'device'
        'bacon' : 'openrecovery-twrp-2.8.0.1-bacon.img',
        'condor' : 'openrecovery-twrp-2.7.1.0-condor.img',
        'deb' : 'openrecovery-twrp-2.8.0.1-deb.img',
        # DO NOT USE TWRP 2.8.6.0 for flo. recovery is reported as 'device'
        'flo' : 'openrecovery-twrp-2.8.0.1-flo.img',
        'grouper' : 'openrecovery-twrp-2.8.0.1-grouper.img',
        'hammerhead' : 'twrp-2.8.6.1-hammerhead.img',
        'm7' : 'openrecovery-twrp-2.8.0.2-m7',
        'maguro' : 'openrecovery-twrp-2.8.0.1-maguro.img',
        'mako' : 'twrp-2.8.6.0-mako.img',
        'shamu' : 'twrp-2.8.6.0-shamu.img',
        'sirius' : 'openrecovery-twrp-2.8.0.1-sirius.img',
        }

    TWRP_LINK = 'http://techerrata.com/browse/twrp2/%(device)s'

    def __init__(self, *args, **kwargs):
        super(Recovery, self).__init__(*args, **kwargs)

    def get_recovery(self, device=None):
        """
        Returns a local path to the recovery image.

        - First checks if there is a version-freeze on the recovery image.
        - Otherwise, queries techerrata.com for the latest twrp image.
        """
        if device in self.DEVICE_TO_IMAGE_NAME:
            return self.get_local_path('recovery/' + self.DEVICE_TO_IMAGE_NAME[device])

        twrp_url = self.latest_twrp_url(device=device)
        if not twrp_url:
            raise Exception('No recovery image available for device "%s"' % device)

        return self.download_client.get_local_path(twrp_url)

    def latest_twrp_url(self, device=None):
        """
        Returns the URL for the latest TWRP image.

        e.g.: http://techerrata.com/file/twrp2/hammerhead/openrecovery-twrp-2.7.0.0-hammerhead.img

        Queries TWRP_LINK.
        """
        twrp_url = self.TWRP_LINK % {'device' : device}
        print >> sys.stderr, 'Searching for TWRP recovery image for %s' % device

        print >> sys.stderr, 'Querying URL: %s' % twrp_url
        twrp_list = urllib.urlopen(twrp_url)
        print >> sys.stderr, 'Parsing TWRP document...'

        # Get TWRP listing.
        soup = BeautifulSoup(twrp_list)

        # Find all .img links (in <a href=""/>).  Also require the path to contain:
        # file/twrp' and the device name.
        images = set([ elm.get('href')
                       for elm in soup.findAll('a')
                       if elm.get('href').endswith('.img') and
                          'file/twrp' in elm.get('href') and
                          device in elm.get('href')
                   ])
        if len(images) == 0:
            raise 'No TWRP recovery images found for device (%s)' % device

        # Assume versions can be lexographically sorted
        images = sorted(images, reverse=True)
        return images[0]

if __name__ == '__main__':
    recovery = Recovery()
    # Test with hammerhead
    print 'Latest twrp URL: %s' %  recovery.latest_twrp_url(device='hammerhead')
    print 'Local path: %s' % recovery.get_recovery(device='hammerhead')
