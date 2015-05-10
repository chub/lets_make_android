#! /usr/bin/python
#
# Strips an signed ZIP archived and replaces with the signing keys of choice.
# It also analyzes, strips, and signs all APKs and JARs within the zip archive
# by detecting the differences among release keys, platform keys, shared keys,
# and media keys.
#
# CM-specific releasekey detection is also updated.  Only NIGHTLY and SNAPSHOT
# builds are affected (which use Android debug keys).

import argparse
import contextlib
from distutils import spawn
import os
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

def get_flags(flags_array=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--infile',
                        type=str,
                        help='the input zipfile'),
    parser.add_argument('--outfile',
                        type=str,
                        help='the output zipfile'),
    parser.add_argument('--signing_keys',
                        type=str,
                        help='the name of new signing keys (release, platform, shared, and ' + \
                        'media keys are required)'),
    parser.add_argument('--force_release',
                        type=str,
                        help='the forced release keypair (with which the OTA is signed)'),
    parser.add_argument('--force_platform',
                        type=str,
                        help='the forced platform keypair (with which the system apps are signed)'),
    parser.add_argument('--force_shared',
                        type=str,
                        help='the forced shared keypair (with which the home/contacts items are signed)'),
    parser.add_argument('--force_media',
                        type=str,
                        help='the forced media keypair (with which download providers are signed)'),
    parser.add_argument('--zipalign',
                        type=str,
                        help='path to the zipalign executable'),
    parser.add_argument('--print_infile_sigs',
                        action='store_true',
                        help='prints the signatures of the input file'),
    parser.add_argument('--verbose',
                        default=False,
                        action='store_true',
                        help='increases verbosity')
    if flags_array:
        return parser.parse_args(flags_array)
    else:
        return parser.parse_args()

def get_temp_dir_root():
    """
    If WORKSPACE is defined, then this means a Jenkins build is executing. Stay
    within the indicated workspace for all temp files.
    """
    if 'WORKSPACE' in os.environ:
        temp_dir_root = os.path.join(os.environ['WORKSPACE'], 'tmpdir')
        # We assume the WORKSPACE directory has already been created
        if not os.path.exists(temp_dir_root):
            os.mkdir(temp_dir_root)
        return temp_dir_root
    else:
        # Fall back to tempfile's defaults.
        return None

class Signature(object):
    """
    Extracts the signature of a signed APK (or zip file).
    """
    def __init__(self, filepath, verbose=False):
        self.filepath = filepath
        self.verbose = verbose

        self.keytool_output = []

    def _get_keytool_output(self):
        if not self.keytool_output:
            cmdline = 'keytool -printcert -jarfile %s' % self.filepath
            if self.verbose:
                print '\tExecuting: %s' % cmdline
            command = subprocess.Popen(cmdline,
                                       shell=True,
                                       stdout=subprocess.PIPE)
            stdout, stderr = command.communicate()
            return_code = command.returncode
            if self.verbose and return_code != 0:
                print '\tReturnCode = %s' % return_code

            # Check that '^Signature:' is found
            for outputline in stdout.splitlines():
                if outputline.startswith('Signature:'):
                    self.keytool_output = stdout.splitlines()
                    break

        return self.keytool_output

    def get_sha1(self):
        for line in self._get_keytool_output():
            if 'SHA1:' in line:
                return line.split()[1]

    def get_owner(self):
        for line in self._get_keytool_output():
            if line.startswith('Owner:'):
                return line[7:]

class ReleaseSignature(Signature):
    """
    Identifies the release key via system/app/HTMLViewer.apk
    """
    def __init__(self, ziproot_path, verbose=None):
        super(ReleaseSignature, self).__init__(
            os.path.join(ziproot_path,
                         'system/app/HTMLViewer.apk'),
            verbose=verbose)

class PlatformSignature(Signature):
    """
    Identifies the Platform key via system/priv-app/SystemUI.apk
    """
    def __init__(self, ziproot_path, verbose=None):
        super(PlatformSignature, self).__init__(
            os.path.join(ziproot_path,
                         'system/priv-app/SystemUI.apk'),
            verbose=verbose)

class SharedSignature(Signature):
    """
    Identifies the shared key via system/priv-app/DownloadProvider.apk
    """
    def __init__(self, ziproot_path, verbose=None):
        super(SharedSignature, self).__init__(
            os.path.join(ziproot_path,
                         'system/priv-app/DownloadProvider.apk'),
            verbose=verbose)

class MediaSignature(Signature):
    """
    Identifies the media key via system/priv-app/Contacts.apk
    """
    def __init__(self, ziproot_path, verbose=None):
        super(MediaSignature, self).__init__(
            os.path.join(ziproot_path,
                         'system/priv-app/Contacts.apk'),
            verbose=verbose)

def get_mime_type(filepath, verbose=False):
    """
    Determines the MIME type of a file using file(1) on the host system.

    When None or empty strings are returned, then the mime type could not be determined.
    """
    cmdline = 'file -b --mime-type "%s"' % filepath
    if verbose:
        print '\tExecuting: %s' % cmdline
    command = subprocess.Popen(cmdline,
                               shell=True,
                               stdout=subprocess.PIPE)
    stdout, stderr = command.communicate()
    return_code = command.returncode
    if verbose:
        print '\tstdout: %r' % stdout
    if return_code != 0:
        raise Exception('file(1) failed to identify %s' % filepath)

        return None

    return stdout.splitlines()[0]

class SignApk(object):
    """
    Signs multiple APKs and ZIPs with the given keypair stem.

    A keypair stem is like 'build/target/product/security/testkey', and is mapped into
    - build/target/product/security/testkey.x509.pem, and
    - build/target/product/security/testkey.pk8

    Calling the constructor will automatically check that both public and
    private keys are available.

    public key is expected to be 'keypair.x509.pem' in PEM format
    private key is expected to be 'keypair.pk8' in DER format
    """
    def __init__(self, keypair=None, flags=None):
        self.verbose = False
        self.zipalign_path = None
        if flags:
            self.verbose = flags.verbose
            self.zipalign_path = flags.zipalign

        if self.zipalign_path and not os.path.exists(self.zipalign_path):
            raise Exception('Invalid zipalign path: %s' % self.zipalign_path)

        self.public_key = '%s.x509.pem' % keypair
        if not os.path.exists(self.public_key):
            raise Exception('Could not find public key file: %s' % self.public_key)

        self.private_key = '%s.pk8' % keypair
        if not os.path.exists(self.private_key):
            raise Exception('Could not find private key file: %s' % self.private_key)

        self.openssl_output = []

    def _get_openssl_output(self):
        if self.openssl_output:
            return self.openssl_output

        if not spawn.find_executable('openssl'):
            print 'openssl not available to print certificate information'
            return self.openssl_output

        command = subprocess.Popen('openssl x509 -in %s -subject -fingerprint' % self.public_key,
                                   shell=True,
                                   stdout=subprocess.PIPE)
        stdout, stderr = command.communicate()
        return_code = command.returncode
        if return_code != 0:
            print 'openssl could not print certificate information'
        else:
            for line in stdout.splitlines()[:2]:
                if line.startswith('subject=') or line.startswith('SHA1 Fingerprint='):
                    self.openssl_output.append(line)

        return self.openssl_output

    def get_sha1(self):
        for line in self._get_openssl_output():
            if line.startswith('SHA1 Fingerprint='):
                return line.split('=')[1]

    def get_owner(self):
        for line in self._get_openssl_output():
            if line.startswith('subject='):
                return line.replace('subject=', '')

    def print_key_info(self, prefix=''):
        """
        Prints signature and subject of key
        """
        if not spawn.find_executable('openssl'):
            print prefix + 'openssl not available to print certificate information'
            return

        command = subprocess.Popen('openssl x509 -in %s -subject -fingerprint' % self.public_key,
                                   shell=True,
                                   stdout=subprocess.PIPE)
        stdout, stderr = command.communicate()
        return_code = command.returncode
        if return_code != 0:
            print prefix + 'openssl could not print certificate information'
        else:
            for line in stdout.splitlines()[:2]:
                print prefix + line

    def sign(self, zipfile):
        """
        Signs zipfile in place.
        """
        signapk = get_local_signapk()
        try:
            new_file = tempfile.mktemp(dir=get_temp_dir_root())

            cmdline = 'java -jar %(signapk_jar)s %(public_key)s %(private_key)s %(unsigned_jar)s %(signed_jar)s' % {
                'signapk_jar': get_local_signapk(),
                'public_key': self.public_key,
                'private_key': self.private_key,
                'unsigned_jar': zipfile,
                'signed_jar': new_file,
            }
            if self.verbose:
                print '\tExecuting: %s' % cmdline
            command = subprocess.Popen(cmdline,
                                       shell=True,
                                       stdout=subprocess.PIPE)
            stdout, stderr = command.communicate()
            return_code = command.returncode
            if return_code != 0:
                raise Exception('Unable to sign %s' % zipfile)

            # Replace zipfile with tempfile
            os.rename(new_file, zipfile)

            # Continue by zipaligning
            self.zipalign_if_defined(zipfile)
        finally:
            if os.path.exists(new_file):
                os.unlink(new_file)

    def zipalign_if_defined(self, zipfile):
        """
        Calls zipalign if the path is defined.
        """
        if not self.zipalign_path:
            if self.verbose:
                print '\tSkipping zipalign - --zipalign flag was not defined'
            return

        try:
            new_file = tempfile.mktemp(dir=get_temp_dir_root())

            cmdline = '%(zipalign)s -v 4 %(input_zip)s %(output_zip)s' % {
                'zipalign' : self.zipalign_path,
                'input_zip' : zipfile,
                'output_zip' : new_file,
            }
            if self.verbose:
                print '\tExecuting: %s' % cmdline
            command = subprocess.Popen(cmdline,
                                       shell=True,
                                       stdout=subprocess.PIPE)
            stdout, stderr = command.communicate()
            return_code = command.returncode
            if return_code != 0:
                raise Exception('Unable to zipalign %s' % zipfile)

            # Replace aligned zipfile with tempfile
            os.rename(new_file, zipfile)
        finally:
            if os.path.exists(new_file):
                os.unlink(new_file)

@contextlib.contextmanager
def make_tempdir(verbose=None):
    """
    Creates a temporary directory and cleans it up after the contextmanager dies.
    """
    temp_dir = tempfile.mkdtemp(dir=get_temp_dir_root())
    if verbose:
        print 'New tempdir: %s' % temp_dir
    yield temp_dir
    shutil.rmtree(temp_dir)

def get_local_signapk():
    """
    Creates the appropriate path for the locally checked-in signapk.jar.
    """
    signapk_path = os.path.join(
        os.path.dirname(__file__),
        '../binaries/host/signapk.jar')
    if not os.path.exists(signapk_path):
        raise Exception('Unable to locate checked in signapk.jar')
    return signapk_path

def get_local_signing_keys(name_of_keypairs=None):
    """
    Returns the fully-qualified path to the signing_keys in the tools/build-utils repository.
    """
    signing_keys_path = os.path.join(
        os.path.dirname(__file__),
        'signing_keys',
        name_of_keypairs)
    if not os.path.exists(signing_keys_path):
        raise Exception('Unable to locate the signing_keys named "%s"' % name_of_keypairs)
    return signing_keys_path

def make_zip(root=None, outfile=None, verbose=None):
    """
    Creates a ZIP archive at outfile from the root directory.

    Note: Avoid changing the CWD.  Doing so without returning may cause issues downstream.
    """
    cmdline = 'zip -r9 %s *' % outfile
    if verbose:
        print '\tFrom %s executing: %s' % (root, cmdline)
    command = subprocess.Popen(cmdline,
                               shell=True,
                               stdout=subprocess.PIPE,
                               cwd=root)
    stdout, stderr = command.communicate()
    return_code = command.returncode
    if verbose:
        for line in stdout.splitlines():
            print '\tstdout: %s' % line
    if return_code != 0:
        raise Exception('Unable to create zip archive from %s' % root)

class ReadOnlyMode(object):
    """
    This mode prints the signatures of the zipfiles and its signed contents.
    """
    def __init__(self, flags):
        self.flags = flags

    def read_only_main(self):
        with make_tempdir(verbose=self.flags.verbose) as tempdir, \
             ZipFile(self.flags.infile, 'r') as inzipfile:

            # Create workspace dir and extract zipfile
            ziproot_path = os.path.join(tempdir, 'ziproot')

            print 'Extracting %s into %s' % (self.flags.infile, ziproot_path)
            inzipfile.extractall(ziproot_path)

            # Determine the 4 keys
            release_signature = ReleaseSignature(ziproot_path, verbose=self.flags.verbose)
            platform_signature = PlatformSignature(ziproot_path, verbose=self.flags.verbose)
            shared_signature = SharedSignature(ziproot_path, verbose=self.flags.verbose)
            media_signature = MediaSignature(ziproot_path, verbose=self.flags.verbose)
            print 'The release key is:'
            print '\t%s' % release_signature.get_sha1()
            print '\t%s' % release_signature.get_owner()
            print 'The platform key is:'
            print '\t%s' % platform_signature.get_sha1()
            print '\t%s' % platform_signature.get_owner()
            print 'The shared key is:'
            print '\t%s' % shared_signature.get_sha1()
            print '\t%s' % shared_signature.get_owner()
            print 'The media key is:'
            print '\t%s' % media_signature.get_sha1()
            print '\t%s' % media_signature.get_owner()

            for root, dirs, files in os.walk(ziproot_path):
                for filename in files:
                    filepath = os.path.join(root, filename)

                    meme_type = get_mime_type(filepath, verbose=self.flags.verbose)
                    if meme_type == 'application/zip':
                        file_signature = Signature(filepath, verbose=self.flags.verbose)
                        sha1 = file_signature.get_sha1()

                        if sha1:
                            print filepath
                            print '\t' + sha1
                            print '\t' + file_signature.get_owner()

class ReadWriteMode(object):
    """
    This mode resigns an OTA zip with four new keys - release, platform, shared, media.
    """
    def __init__(self, flags):
        self.flags = flags

    def init_signers(self, flags):
        """
        Instantiates all signers.
        """
        # Instantiate release keypair
        release_keypair = self.flags.force_release
        if not release_keypair:
            release_keypair = os.path.join(get_local_signing_keys(self.flags.signing_keys),
                                           'release')
        self.release_signer = SignApk(flags=self.flags, keypair=release_keypair)

        # Instantiate platform keypair
        platform_keypair = self.flags.force_platform
        if not platform_keypair:
            platform_keypair = os.path.join(get_local_signing_keys(self.flags.signing_keys),
                                            'platform')
        self.platform_signer = SignApk(flags=self.flags, keypair=platform_keypair)

        # Instantiate shared keypair
        shared_keypair = self.flags.force_shared
        if not shared_keypair:
            shared_keypair = os.path.join(get_local_signing_keys(self.flags.signing_keys),
                                          'shared')
        self.shared_signer = SignApk(flags=self.flags, keypair=shared_keypair)

        # Instantiate media keypair
        media_keypair = self.flags.force_media
        if not media_keypair:
            media_keypair = os.path.join(get_local_signing_keys(self.flags.signing_keys),
                                         'media')
        self.media_signer = SignApk(flags=self.flags, keypair=media_keypair)

        # Print the cert info
        print 'The new release key will be:'
        print '\t' + self.release_signer.get_sha1()
        print '\t' + self.release_signer.get_owner()
        print ''
        print 'The new platform key will be:'
        print '\t' + self.platform_signer.get_sha1()
        print '\t' + self.platform_signer.get_owner()
        print ''
        print 'The new shared key will be:'
        print '\t' + self.shared_signer.get_sha1()
        print '\t' + self.shared_signer.get_owner()
        print ''
        print 'The new media key will be:'
        print '\t' + self.media_signer.get_sha1()
        print '\t' + self.media_signer.get_owner()
        print ''

    def replace_cyanogenmod_releasekey(self, ziproot=None):
        """
        If the ziproot has a cyanogenmod release key, then the local_signing_key directory will be
        checked.  If the replacement key is missing, this function will fail.

        If the ziproot has no cyanogenmod release key, then this method is a no-op.
        """
        old_releasekey = os.path.join(
            ziproot,
            'META-INF',
            'org',
            'cyanogenmod',
            'releasekey')

        if os.path.exists(old_releasekey):
            new_releasekey = os.path.join(
                get_local_signing_keys(self.flags.signing_keys),
                'releasekey')
            if not os.path.exists(new_releasekey):
                raise Exception('Cannot replace old releasekey. The selected signing_keys do not a replacement releasekey.')

            # Overwrite the old releasekey with the new releasekey
            print 'Replacing META-INF/org/cyanogenmod/releasekey'
            shutil.copyfile(new_releasekey, old_releasekey)

    def read_write_main(self):
        if not self.flags.outfile:
            raise Exception('--outfile needed')
        elif not os.path.exists(os.path.dirname(self.flags.outfile)):
            raise Exception('Directory for --outfile %s does not exist' % os.path.dirname(self.flags.outfile))

        # Check that the required tools are installed.
        if not spawn.find_executable('java'):
            raise Exception('Unable to find java in PATH')
        if not spawn.find_executable('zip'):
            raise Exception('Unable to find zip in PATH')
        # signapk is checked differently since it is checked into the repository
        get_local_signapk()

        self.init_signers(self.flags)

        # Start
        with make_tempdir(verbose=self.flags.verbose) as tempdir, \
             ZipFile(self.flags.infile, 'r') as inzipfile:

            # Create workspace dir and extract zipfile
            ziproot_path = os.path.join(tempdir, 'ziproot')

            print 'Extracting %s into %s' % (self.flags.infile, ziproot_path)
            inzipfile.extractall(ziproot_path)

            # Determine the 4 keys
            release_signature = ReleaseSignature(ziproot_path, verbose=self.flags.verbose)
            platform_signature = PlatformSignature(ziproot_path, verbose=self.flags.verbose)
            shared_signature = SharedSignature(ziproot_path, verbose=self.flags.verbose)
            media_signature = MediaSignature(ziproot_path, verbose=self.flags.verbose)
            print 'The old release key is:'
            print '\t' + release_signature.get_sha1()
            print '\t' + release_signature.get_owner()
            print ''
            print 'The old platform key is: '
            print '\t' + platform_signature.get_sha1()
            print '\t' + platform_signature.get_owner()
            print ''
            print 'The old shared key is:   '
            print '\t' + shared_signature.get_sha1()
            print '\t' + shared_signature.get_owner()
            print ''
            print 'The old media key is:    '
            print '\t' + media_signature.get_sha1()
            print '\t' + media_signature.get_owner()
            print ''
            new_signer_map = {
                release_signature.get_sha1() : self.release_signer,
                platform_signature.get_sha1() : self.platform_signer,
                shared_signature.get_sha1() : self.shared_signer,
                media_signature.get_sha1() : self.media_signer,
            }

            self.replace_cyanogenmod_releasekey(ziproot=ziproot_path)

            # Iterate through all the zip file contents
            for root, dirs, files in os.walk(ziproot_path):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    pretty_filepath = filepath.replace(ziproot_path, '')

                    meme_type = get_mime_type(filepath, verbose=self.flags.verbose)
                    if meme_type != 'application/zip':
                        # Not a zip archive
                        continue

                    file_signature = Signature(filepath, verbose=self.flags.verbose)
                    sha1 = file_signature.get_sha1()

                    if not sha1:
                        # Not signed
                        continue

                    if self.flags.verbose:
                        print filepath
                        print '\t' + sha1
                        print '\t' + file_signature.get_owner()

                    # Retrieve the correct signer. Skip stripping if the signature is not recognized.
                    new_signer = new_signer_map.get(sha1, None)
                    if new_signer:
                        print pretty_filepath
                        print '\tstripping ' + sha1
                        print '\tresigning ' + new_signer.get_sha1()
                        new_signer.sign(filepath)

            # Zip up the ziproot
            print 'Creating zip archive at %s' % self.flags.outfile
            make_zip(root=ziproot_path, outfile=self.flags.outfile, verbose=self.flags.verbose)
            print 'Signing zip archive with release key'
            self.release_signer.sign(self.flags.outfile)

        print 'Done.'
        print ''
        print 'Summary:'
        print ' Input: %s' % self.flags.infile
        print 'Output: %s' % self.flags.outfile

class ResignOtaZip(object):
    @classmethod
    def resign_ota_zip(cls, flags):
        # Check for required programs
        if not spawn.find_executable('keytool'):
            raise Exception('Unable to find keytool in PATH')

        # Check args
        if not flags.infile:
            raise Exception('--infile needed')
        elif not os.path.exists(flags.infile):
            raise Exception('--infile %s does not exist' % flags.infile)

        if flags.print_infile_sigs and flags.outfile is None:
            romode = ReadOnlyMode(flags)
            romode.read_only_main()
        else:
            rwmode = ReadWriteMode(flags)
            rwmode.read_write_main()

if __name__ == '__main__':
    flags = get_flags()

    ResignOtaZip.resign_ota_zip(flags)
