from .download_client import DownloadClient

class BlobsCache(object):
    """
    A blobs cache can interact with an S3 bucket path (s3://your-bucket/some/file/prefix/) or an
    HTTP prefix ('https://raw.githubusercontent.com/chub/lma_blobs/').
    """
    BLOBS_BASE = 'https://raw.githubusercontent.com/chub/lma_blobs/'

    def __init__(self, download_client=None):
        if download_client is None:
            download_client = DownloadClient()
        self.download_client = download_client

    def get_local_path(self, image_name):
        s3_path = '%s%s' % (self.BLOBS_BASE, image_name)
        return self.download_client.get_local_path(s3_path)
