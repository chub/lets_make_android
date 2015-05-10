from .blobs_cache import BlobsCache

class NoSuperSuException(Exception): pass

class SuperSU(BlobsCache):
    IMAGE = 'UPDATE-SuperSU-v2.46.zip'

    def __init__(self, *args, **kwargs):
        super(SuperSU, self).__init__(*args, **kwargs)

    def get_supersu_zip(self):
        """
        Returns the local path to the SuperSU zip.
        """
        return self.get_local_path(self.IMAGE)
