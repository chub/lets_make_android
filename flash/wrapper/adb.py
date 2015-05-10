import subprocess
import time

from .console_wrapper import ConsoleWrapper

class AdbCommand(object):
    """
    This wrapper retries until a clean execution happens (return code of 0).

    For non-idempotent commands, automatic retries can be disabled by setting attempts.
    """
    def __init__(self, serial, verbose, raw_command=None, shell_command=None, attempts=3):
        line = self.construct_line(serial, raw_command=raw_command, shell_command=shell_command)

        for i in xrange(attempts):
            if verbose:
                if i < 1:
                    print '\tExecuting: %s' % line
                else:
                    print '\tExecuting (retry %d): %s' % (i+1, line)
            command = subprocess.Popen(line,
                                       shell=True,
                                       stdout=subprocess.PIPE)
            self.stdout, self.stderr = command.communicate()
            self.returncode = command.returncode

            if verbose and self.returncode != 0:
                print '\tReturnCode = %s' % self.returncode

            # Break if successful
            if self.returncode == 0:
                break

            # If the loop will restart, then we should wait one second
            if i+1 < attempts:
                time.sleep(1)

    @classmethod
    def construct_line(cls, serial, raw_command=None, shell_command=None):
        if raw_command is not None and shell_command is not None:
            raise AdbCommandException('raw_command ("%s") shell_command ("%s") cannot both be populated.' % \
                                          (raw_command, shell_command))

        if raw_command is None and shell_command is None:
            raise AdbCommandException('No command passed.')

        # Unlike AdbShellCommand, quotes are not needed.  There is no
        # redirection operators that need to be passed to the device.
        if raw_command:
            line = 'adb -s "%s" %s' % (serial, raw_command)
        else:
            line = 'adb -s "%s" shell "%s"' % (serial, shell_command)
        return line

class AdbCommandException(Exception):
    """
    Used to indicate a non-zero return-code.

    Since this exception is a checked exception, AdbCommand() commands and
    their callers need to be updated to properly catch this.
    """
    pass

class NoDeviceException(Exception):
    def __unicode__():
        return u"NoDeviceException"

    def __str__():
        return "NoDeviceException"

class AdbSerial(ConsoleWrapper):
    def __init__(self, serial=None, verbose=None):
        ConsoleWrapper.__init__(self, verbose=verbose)
        self.serial = serial

    def shell(self, in_command, attempts=3, use_exception=False):
        out_command = AdbCommand(self.serial, self.verbose, shell_command=in_command)

        # If the caller can handle exceptions, raise AdbCommandException if return code is not 0.
        if use_exception and out_command.returncode != 0:
            raise AdbCommandException()

        # Legacy behavior: return the command
        return out_command

    def getprop(self, property):
        """Returns the property requested. None if there's nothing."""
        prop = self.shell('getprop %s' % property)
        if prop.returncode != 0:
            raise Exception('Could not retrieve property %s. Error: %s' %
                            (property, prop.returncode))

        return prop.stdout.strip()

    def getprop_file(self, property, prop_file=None):
        """
        Returns a property defined in the indicated file.

        getprop() uses the getprop utility, which reads from /defaults.prop if the device
        is in recovery mode.
        """
        prop_cmd = self.shell('grep ^%s %s' % (property, prop_file))
        if prop_cmd.returncode != 0:
            raise Exception('Unable to read %s' % prop_file)

        prop_line = prop_cmd.stdout.strip()
        if prop_line.startswith('%s=' % property):
            return prop_line.replace('%s=' % property, '', 1)
        return ''

    def getprop_system(self, property):
        """
        Convenience method for /system/build.prop.

        Assumes /system has already been mounted.
        """
        return self.getprop_file(property, prop_file='/system/build.prop')

    def tap_point(self, coords):
        """Simulates a screen tap in the Android display coordinate space"""
        tap = self.shell('input tap %s %s' % (coords[0], coords[1]))
        if tap.returncode != 0:
            raise Exception('Tap command failed: %s' % tap.returncode)

    def enter_text(self, text):
        """Simulates entering text"""
        cmd = 'input text "%s"' % text
        textcmd = self.shell(cmd)
        if textcmd.returncode != 0:
            raise Exception('Entering text command failed: %s' % textcmd.returncode)

    def send_key_event(self, key_event):
        """
        Sends a raw keyevent.

        Find definitions here: https://developer.android.com/reference/android/view/KeyEvent.html
        """
        key_event_cmd = self.shell('input keyevent %d' % key_event)
        if key_event_cmd.returncode != 0:
            raise Exception('Sending key event command %d failed: %s' %
                            (key_event, key_event_cmd.returncode))

    def get_adb_root(self):
        """Runs 'adb root'"""
        adbrootcmd = AdbCommand(self.serial, self.verbose, raw_command='root')
        if adbrootcmd.returncode != 0:
            raise Exception('Could not execute root. Failed: %s' % adbrootcmd.returncode)

        if 'adbd cannot run as root in production builds' in adbrootcmd.stdout:
            print 'WARNING: Device\'s adb is not root-escalated. Results may vary.'

        # If adbd needs to restart as root, sleep for a moment to give the adb
        # daemon a chance to restart itself. Otherwise we will busy-spamming adb
        # commands while it is unavailable.
        if 'restarting adbd as root' in adbrootcmd.stdout:
            time.sleep(3)

    def setup_wifi(self, wifiap, wifipassword):
        """Sets up wifi on the device"""
        wifi_cmd = self.shell('nbwifi "%s" "%s"' % (wifiap, wifipassword))
        if wifi_cmd.returncode != 0:
            raise Exception('Unable run "nbwifi" on device.')

        for line in wifi_cmd.stdout.split('\n'):
            if line.find('nbwifi: not found') != -1:
                raise Exception('Unable run "nbwifi" on device.')

    def is_wifi_connected(self):
        """Checks if any wifi state machines are in NotConnectedStates or DisconnectedStates."""
        dumpsys_wifi_cmd = self.shell('dumpsys wifi | grep -e "curState=NotConnectedState"  -e "curState=DisconnectedState"')
        return dumpsys_wifi_cmd.returncode != 0

    def wait_for_wifi(self):
        """Blocks for up to 30 seconds until the Wifi subsystem is connected."""
        for i in xrange(30):
            if self.is_wifi_connected():
                return
            time.sleep(1)
        raise Exception('Timed out waiting for wifi.')

    def has_telephony(self):
        """Returns True if the device GCM or CDMA access, false if not, None if ambiguous."""
        telephony_cmd = self.shell('dumpsys connectivity')
        if telephony_cmd.returncode != 0:
            print 'Cannot tell whether device has telephony! Error: %s' % \
                telephony_cmd.returncode
            return None

        # If "MOBILE" is present, then the device has telephony
        return telephony_cmd.stdout.find('NetworkStateTracker for MOBILE') != -1

    def reboot(self, mode=None):
        reboot_cmdline = 'reboot'
        if mode is not None:
            reboot_cmdline = 'reboot %s' % (mode)

        cmd = AdbCommand(self.serial, self.verbose, raw_command=reboot_cmdline)
        if cmd.returncode != 0:
            print 'Could not reboot. Failed: %s' % cmd.returncode
            return False

        return True

    def push(self, local_path, remote_path):
        """Pushes local_path to remote_path on the device."""
        cmdline = 'push %s %s' % (local_path, remote_path)
        cmd = AdbCommand(self.serial, self.verbose, raw_command=cmdline)
        if cmd.returncode != 0:
            print 'Could not push %s. Failed: %s' % (local_path, cmd.returncode)
            return False
        return True

    def install(self, local_path):
        """Installs the apk indicated in the local_path."""
        cmdline = 'install -r %s' % (local_path)
        cmd = AdbCommand(self.serial, self.verbose, raw_command=cmdline)
        if cmd.returncode != 0:
            print 'Could not install -r %s. Failed: %s' % (local_path, cmd.returncode)
            return False
        return True

    def wait_for_device(self):
        """Waits for a device to start adb."""
        # Capture stderr so that we can throw away the silly stderr message
        # when more than one device is present.
        waitfor = AdbCommand(self.serial, self.verbose, raw_command='wait-for-device')
        if waitfor.returncode != 0:
            self.print_verbose('ReturnCode = %s' % waitfor.returncode)
            # This is not actually a real error...
            if 'more than one device and emulator' in waitfor.stderr:
                return True
            print 'Wait command failed: %s' % waitfor.returncode
            return False
        return True

    def wait_for_recovery(self):
        """
        Waits for a recovery image to start adb.

        This is because adb does not respond to wait-for-device in recovery.
        This method was originally implemented in flash-device-latest and thoroughly tested.
        """
        # Step 1: Execute dmesg, and look for "Linux"
        # - If device is missing, adb shell returns "device not found"
        # - If dmesg is not ready, dmesg returns "klogctl: Operation not permitted"
        while True:
            dmesg = self.shell('dmesg')

            if 'Linux' in dmesg.stdout:
                break

            self.print_when_not_verbose('.')
            time.sleep(1)

        # Step 2 (Clockwork-specific): Make sure /cache/recovery/log is visible.
        # - Reject message "/cache/recovery/log: No such file or directory"
        self.wait_for_path_or_mount(path='/cache/recovery/log')

    def is_mount_point_mounted(self, mount=None):
        """
        Returns true if the indicated mountpoint is mounted.

        Note: This method only accepts the following mount(1) format:
        -  /dev/block/mmcblk0p25 on /system type ext4 (rw,seclabel,relatime,data=ordered)
        """
        mount_point = self.shell('mount', use_exception=True)

        mount_grep = 'on %s type ' % mount
        if mount_grep in mount_point.stdout:
            mounted = True
        else:
            mounted = False

        self.print_verbose('is_mount_point_mounted %s : %s' % (mount, mounted))
        return mounted

    def path_exists(self, path=None):
        """
        Returns true if a path exists.  Otherwise, returns false.
        """
        ls_path = self.shell('ls %s' % path, use_exception=True)
        if 'No such file or directory' in ls_path.stdout:
            return False
        return True

    def wait_for_path_or_mount(self, path=None, mount=None, debounce=1):
        """
        Blocks until a path or a mount exists on the device.

        If debounce is set to a positive integer N, then the path or mount must
        return the same result N times before this function returns.
        """
        if path is None and mount is None:
            self.print_verbose('WARNING: wait_for_path_or_mount was called with no arguments')
            return

        true_count = 0

        while True:
            if path is not None:
                # Make sure the requested path is visible.
                # - Reject message "${path}: No such file or directory"
                try:
                    if self.path_exists(path=path):
                        true_count += 1
                        if true_count >= debounce:
                            return
                except AdbCommandException:
                    # We should wait if shell did not execute.
                    pass

            if mount is not None:
                try:
                    if self.is_mount_point_mounted(mount=mount):
                        true_count += 1
                        if true_count >= debounce:
                            return
                except AdbCommandException:
                    # We should wait if shell did not execute.
                    pass

            self.print_when_not_verbose('.')
            time.sleep(1)

    # The 'dumpsys' command on the device can tell us which activity is front most.
    # Parse its output. It looks something like this...
    #
    # """
    # Running activities (most recent first):
    #    TaskRecord{42756e08 #3 A com.google.android.setupwizard U 0}
    #      Run #1: ActivityRecord{425f1030 u0 com.google.android.setupwizard/.SimMissingActivity}
    #      Run #0: ActivityRecord{4276fbc8 u0 com.google.android.setupwizard/.SetupWizardActivity}
    # """
    #
    # For this case, we want to return ".SimMissingActivity". Returns None on failure.
    # Raises NoDeviceException if no adb device is available.
    def getForegroundActivity(serial = None):
        """
        Gets the name of the Android app Activity that is in the foreground.
        """
        if serial is not None:
            cmd = "adb -s {} shell dumpsys activity".format(serial)
        else:
            cmd = "adb shell dumpsys activity"
        dumpsys = subprocess.Popen(cmd, shell = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        output, errout = dumpsys.communicate()
        if dumpsys.returncode != 0:
            if 'error: device not found' in errout:
                raise NoDeviceException()
            print("Dumpsys command failed: {}".format(dumpsys.returncode))
            return None

        # 'dumpsys activity' includes the current focused activity.  Search for the name.
        apos = output.find("mFocusedActivity: ActivityRecord")
        if apos == -1:
            return None

        # Isolate the mFocusedActivity line.
        # In 4.2, it looks like this:
        #   mFocusedActivity: ActivityRecord{41403ea0 u0 com.google.android.setupwizard/.WelcomeActivity}
        # In 4.4, it looks like this:
        #   mFocusedActivity: ActivityRecord{41a40b60 u0 com.google.android.setupwizard/.WelcomeActivity t3}
        line = output[apos:].split("\n")[0]
        fullName = re.search("{[0-9a-f]{8} .. ([^ ]*)[ }]", line).group(1)
        return fullName.split("/")[1]
