#! /usr/bin/python

import hashlib
import os
import sys

from .adb import AdbSerial
from .console_wrapper import ConsoleWrapper
from .device import Device

def hashfile(filename, hash_type=hashlib.md5):
    hasher = hash_type()
    with open(filename, 'rb') as file_h:
        for chunk in iter(lambda: file_h.read(128 * hasher.block_size), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

class OpenRecoveryScript(ConsoleWrapper):
    """
    Creates an OpenRecoveryScript.

    Reboots device to recovery mode on write.

    Syntax: http://www.teamw.in/OpenRecoveryScript
    """
    ZIP_PREFIX = "/sdcard/Download/openrecoveryscript"

    def __init__(self, serial, verbose=False):
        ConsoleWrapper.__init__(self, verbose=verbose)
        self.serial = serial

        self.adb = AdbSerial(serial=self.serial,
                             verbose=self.verbose)
        self.device = Device(serial=self.serial,
                             verbose=self.verbose)

        # Ordered commands to execute
        self.commands = []

        # Tuples containing files paths: (computer_path, device_path)
        self.zipfiles = []

        # Set of mounted points
        self.mounted_points = set()

        # Where we should reboot to, if set
        self.reboot_to_request = None

    def wipe_dalvik(self):
        self.commands.append('wipe dalvik')

    def wipe_cache(self):
        self.commands.append('wipe cache')

    def wipe_userdata(self):
        self.commands.append('wipe data')

    def reboot_to(self, reboot_arg):
        if self.reboot_to_request is not None:
            raise Exception('reboot_to was previously called with %s' % self.reboot_to_request)

        if reboot_arg in ['recovery', 'system', 'bootloader']:
            self.reboot_to_request = reboot_arg
        else:
            raise Exception('Unknown reboot argument "%s"' % reboot_arg)

    def mount(self, mpoint):
        """
        Mount requested mount point if not already mounted.
        """
        if mpoint not in self.mounted_points:
            self.commands.append('mount %s' % mpoint)
            self.mounted_points.add(mpoint)

    def unmount(self, mpoint):
        """
        Unmount requested mount point if mounted.
        """
        if mpoint in self.mounted_points:
            self.commands.append('unmount %s' % mpoint)
            self.mounted_points.remove(mpoint)

    def unmount_all(self):
        """
        Unmount all interactively mounted partitions.
        """
        # Make a copy of the set
        for mpoint in set(self.mounted_points):
            self.unmount(mpoint)

    def delete_file(self, full_path):
        self.commands.append('cmd rm %s' % full_path)

    def install_zip(self, zip_file):
        if not os.path.isfile:
            raise Exception('Cannot install zip, path is not a file: "%s"' % zip_file)
        basename = os.path.basename(zip_file)
        remote_file = '%s/%s' % (self.ZIP_PREFIX, basename)
        self.zipfiles.append((zip_file, remote_file))
        self.commands.append('install %s' % remote_file)

    def install_file(self, local_file, final_remote_path):
        """
        Installs any file to the device.
        """
        basename = os.path.basename(local_file)
        remote_file = '%s/%s' % (self.ZIP_PREFIX, basename)
        self.zipfiles.append((local_file, remote_file))
        self.commands.append('cmd cp %s %s' % (remote_file, final_remote_path))

    def files_match(self, local_file, remote_file):
        """
        Returns True when md5sum of local file matches md5sum of remote file.
        """
        remote_file_md5sum_cmd = self.adb.shell('md5sum %s 2> /dev/null' % remote_file)
        if remote_file_md5sum_cmd.returncode != 0:
            return False

        remote_file_md5sum = remote_file_md5sum_cmd.stdout.strip()
        if not remote_file_md5sum:
            return False

        print 'Remote MD5: %s' % remote_file_md5sum
        local_file_md5sum = hashfile(local_file)
        print ' Local MD5: %s  %s' % (local_file_md5sum, local_file)
        return remote_file_md5sum.startswith(local_file_md5sum)

    def execute(self):
        self.device.reboot_to_recovery()
        self.adb.wait_for_recovery()

        # Upload the files
        for local_file, remote_file in self.zipfiles:
            if not self.files_match(local_file, remote_file):
                rv = self.adb.push(local_file, remote_file)
                if not rv:
                    raise Exception('Unable to upload file: %s to %s' % (local_file, remote_file))
                # Sanity check uploaded file
                if not self.files_match(local_file, remote_file):
                    raise Exception('Uploaded file did not match in MD5: %s to %s' % (local_file, remote_file))

        # Create script
        self.adb.shell('rm /cache/recovery/openrecoveryscript')
        # Append cleanup and reboot commands
        self.unmount_all()
        if self.reboot_to_request is not None:
            self.commands.append('reboot %s' % self.reboot_to_request)

        for line in self.commands:
            self.adb.shell('echo \'%s\' >> /cache/recovery/openrecoveryscript' % line)

        # Execute commands by rebooting into recovery again
        self.device.reboot_to_recovery(forced=True)
