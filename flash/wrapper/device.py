import os
import re
import subprocess
import time

from .adb import AdbSerial
from .console_wrapper import ConsoleWrapper
from .fastboot import Fastboot

from lib.download_client import DownloadClient
from lib.recovery import Recovery

class Device(ConsoleWrapper):
    def __init__(self, serial, verbose=False):
        ConsoleWrapper.__init__(self, verbose=verbose)
        self.serial = serial
        self.serial_pattern = re.compile("%s\s+" % serial)

    def _parse_get_mode(self, cmdline):
        cmd = subprocess.Popen(
            cmdline, shell=True, stdout=subprocess.PIPE)
        stdout, stderr = cmd.communicate()

        if cmd.returncode != 0:
            self.print_verbose('Executed: %s' % cmdline)
            self.print_verbose("ReturnCode: %d" % cmd.returncode)
            return None

        for line in stdout.splitlines():
            serial_match = self.serial_pattern.match(line)
            if serial_match is not None:
                return line.split()[1]

        return None

    def _get_adb_mode(self):
        return self._parse_get_mode("adb devices -l")

    def _get_fastboot_mode(self):
        return self._parse_get_mode("fastboot devices -l")

    def get_mode(self, get_mode_timeout=10):
        """
        Retrieve device mode. Wait no more than 10 seconds for devices to register.

        Note: bacon devices take at least 15 seconds to start when TWRP is first installed.
        Callers should manage this.
        """
        self.print_verbose_nonewline('Reading device mode .')
        for i in xrange(get_mode_timeout):
            mode = self._get_adb_mode()
            if mode is not None or mode == '':
                print('. %s' % mode)
                return mode

            mode = self._get_fastboot_mode()
            if mode is not None or mode == '':
                print('. %s' % mode)
                return mode

            self.print_verbose_nonewline('.')
            time.sleep(1)

        # Use hard-coded timeout
        mode = "timedout"
        print('. %s' % mode)
        return mode

    def reboot_to_recovery(self, forced=False):
        """Reboots device into recovery mode.

        If forced is True, then a device in recovery mode will still be rebooted.
        This should be used sparingly.

        Determines the current mode of the device, and executes the appropriate command.

        Recovery images will be uploaded for devices in fastboot mode.
        If the recovery image is not locally available, this method may trigger a download.

        Returns:
            True if the device reboots, or if the device is already in recovery mode.
            False otherwise.
        """
        current_mode = self.get_mode()
        self.print_verbose("reboot_to_recovery: %s is in %s mode (forced=%s)" % (
            self.serial, current_mode, forced))

        if current_mode == "fastboot":
            fastboot = Fastboot(serial=self.serial, verbose=self.verbose)

            if not fastboot.is_unlocked():
                raise Exception("Device is not unlocked.  Please unlock with 'fastboot oem unlock' to continue")

            model = fastboot.getvar_product()
            recovery_path = Recovery().get_recovery(device=model)

            if fastboot.boot(recovery_path) is False:
                print "reboot_to_recovery: Cannot reboot into recovery"
                return False
        elif current_mode == "recovery" and not forced:
            self.print_verbose("reboot_to_recovery: %s is already in recovery mode" % self.serial)
        elif current_mode == "device" or \
             (current_mode == "recovery" and forced):
            adb = AdbSerial(serial=self.serial,
                            verbose=self.verbose)
            if adb.reboot(mode="recovery") is False:
                print "reboot_to_recovery: Cannot reboot into recovery"
                return False
        else:
            print "reboot_to_recovery: Unknown mode %s" % current_mode
            return False

        while True:
            # Wait for the device, as long as it takes.
            current_mode = self.get_mode(get_mode_timeout=60)
            if current_mode != "recovery":
                continue
            self.print_verbose("%s is in %s mode" % (self.serial, current_mode))
            break

        return True

    def reboot_to_fastboot(self, forced=True):
        """
        Reboots device into fastboot mode.

        If forced is True, then the device is rebooted even if already in fastboot mode.

        Returns:
            True when all commands succeed, false otherwise.

        Caveat:
            This method may return True before the device is in fastboot mode.
        """
        current_mode = self.get_mode()
        self.print_verbose("reboot_to_fastboot: %s is in %s mode (forced=%s)" % (
                self.serial, current_mode, forced))

        if current_mode == "fastboot":
            if forced:
                fastboot = Fastboot(serial=self.serial, verbose=self.verbose)
                fastboot.reboot(mode='reboot-bootloader')
            else:
                self.print_verbose("reboot_to_fastboot: %s is already in fastboot mode" % self.serial)
        elif current_mode == "recovery":
            adb = AdbSerial(serial=self.serial,
                            verbose=self.verbose)
            if adb.reboot(mode="bootloader") is False:
                print "reboot_to_fastboot: Cannot reboot into fastboot"
                return False
        elif current_mode == "device":
            adb = AdbSerial(serial=self.serial,
                            verbose=self.verbose)
            if adb.wait_for_device() is False:
                print "reboot_to_fastboot: Cannot wait-for-device"
                return False

            if adb.reboot(mode="bootloader") is False:
                print "reboot_to_fastboot: Cannot reboot into fastboot"
                return False
        else:
            print "reboot_to_fastboot: Unknown mode %s" % current_mode
            return False

        return True

    def reboot_to_device(self):
        """Reboots device into Android.

        Returns:
            True when all commands succeed, false otherwise.

        Caveat:
            This method may return True before the device is in device mode.
        """
        current_mode = self.get_mode()
        self.print_verbose("reboot_device: %s is in %s mode" % (self.serial, current_mode))

        if current_mode == "fastboot":
            fastboot = Fastboot(serial=self.serial, verbose=self.verbose)
            if not fastboot.is_unlocked():
                raise Exception("Device is not unlocked.  Please unlock with 'fastboot oem unlock' to continue")
            if fastboot.reboot() is False:
                print "reboot_device: Cannot reboot into device"
                return False
        elif current_mode == "recovery":
            adb = AdbSerial(serial=self.serial,
                            verbose=self.verbose)
            if adb.reboot() is False:
                print "reboot_device: Cannot reboot into device"
                return False
        elif current_mode == "device":
            self.print_verbose("reboot_device: %s is already in device mode" % self.serial)
        else:
            print "reboot_device: Unknown mode %s" % current_mode
            return False

        return True

    def recovery_sideload(self, sideload_file):
        """
        Automatically sideloads a zipfile, and restarts device mode.
        """
        adb = AdbSerial(serial=self.serial,
                        verbose=self.verbose)
        self.reboot_to_recovery()
        adb.wait_for_recovery()

        # Remove old zips from cache partition
        adb.shell('rm /cache/*.zip')

        basename = os.path.basename(sideload_file)
        rv = adb.push(sideload_file, '/cache/%s' % basename)
        if not rv:
            print "recovery_sideload: Could not upload %s" % basename
            return False

        adb.shell('echo --update_package=/cache/%s > /cache/recovery/command' %
                  basename)
        self.reboot_to_recovery(forced=True)

    def wait_for_device_then_reboot_to_recovery(self):
        """
        Waits until the device enters device mode or unauthorized mode.

        'timedout' can occur if the CM ROM is in default non-root mode.

        If device is unauthorized, prompt user to intervene.
        """
        while True:
            mode = self.get_mode()
            if mode == 'unauthorized' or mode == 'offline':
                print "Device has adb locked. Please accept to continue installation."
            elif mode == 'device':
                return self.reboot_to_recovery()
            elif mode == 'timedout':
                print "Cannot detect device. Please complete onboarding screen and enable adb mode."
            # We expect the device to be rebooting a new rom and dexopting.  This takes a while.
            time.sleep(5)

def main():
    d = Device('030e5d6f08ea6153', verbose=True)
    d.reboot_to_fastboot()
    d.reboot_to_recovery()
    d.reboot_to_device()

if __name__ == '__main__':
    main()
