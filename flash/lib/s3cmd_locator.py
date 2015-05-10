import os
import subprocess

class S3CmdLocatorException(Exception): pass

class S3CmdLocator(object):
    """
    Locates and checks that s3cmd is properly installed and configured.
    """
    @classmethod
    def get_path(cls):
        """
        Placeholder for more complicated logic, but assume s3cmd is already in the PATH.
        """
        return 's3cmd'
