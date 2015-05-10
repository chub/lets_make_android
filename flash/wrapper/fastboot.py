import subprocess

from .console_wrapper import ConsoleWrapper

class FastbootCommandException(Exception): pass

class Fastboot(ConsoleWrapper):
    def __init__(self, serial=None, verbose=None):
        ConsoleWrapper.__init__(self, verbose=verbose)
        self.serial = serial

    def reboot(self, mode="reboot"):
        if self.serial is None:
            cmdline = "fastboot %s" % mode
        else:
            cmdline = "fastboot -s %s %s" % (self.serial, mode)

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)

    def boot(self, kernel, just_flashed_recovery=None):
        # Always flash the recovery sector when doing this trick.
        # hammerhead devices like to forget what recovery they're coming from.
        # (Skip if just_flashed_recovery is True.)
        if just_flashed_recovery is not True:
            self.flash("recovery", kernel)

        if self.serial is None:
            cmdline = "fastboot boot %s" % kernel
        else:
            cmdline = "fastboot -s %s boot %s" % (self.serial, kernel)

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)

    def flash(self, partition, filename):
        if self.serial is None:
            cmdline = "fastboot flash %s %s" % (partition, filename)
        else:
            cmdline = "fastboot -s %s flash %s %s" % (self.serial, partition, filename)

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)

    def getvar(self, param, use_exception=False):
        if self.serial is None:
            cmdline = "fastboot getvar %s" % param
        else:
            cmdline = "fastboot -s %s getvar %s" % (self.serial, param)

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)
            if use_exception:
                raise FastbootCommandException()
            return None

        for line in stdout.splitlines():
            if line.startswith("%s: " % param):
                return line.split()[1]

        # Also check stderr.  Don't know why getvar writes to stderr for this.
        for line in stderr.splitlines():
            if line.startswith("%s: " % param):
                line_split = line.split()

                # Return None if there is no value
                if len(line_split) >= 2:
                    return line.split()[1]
                else:
                    return None

        self.print_verbose("getvar: Unable to retrieve %s" % param)
        return None

    def getvar_product(self):
        """
        Note: the bootloader can report incorrect products.

        bacon devices report 'MSM8974' as the product and '' as the variant
        """
        product = self.getvar('product')
        if product == 'MSM8974':
            # This can be a bacon (OnePlus One) device. Check the variant (which should be empty).
            variant = self.getvar('variant')
            if variant is None:
                product = 'bacon'
        return product

    def get_oem_device_info(self):
        """
        Returns a map of all the device-info.

        # On bacon
        $ fastboot oem device-info > /dev/null
        ...
        (bootloader)    Device tampered: true
        (bootloader)    Device unlocked: true
        (bootloader)    Charger screen enabled: false
        OKAY [  0.005s]
        finished. total time: 0.005s

        # On hammerhead
        $ fastboot oem device-info > /dev/null
        ...
        (bootloader)    Device tampered: false
        (bootloader)    Device unlocked: true
        (bootloader)    off-mode-charge: true
        OKAY [  0.004s]
        finished. total time: 0.004s
        """
        device_info = {}

        if self.serial is None:
            cmdline = "fastboot oem device-info"
        else:
            cmdline = "fastboot -s %s oem device-info" % (self.serial)

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)
            return device_info

        # Parse "variable: value" that are prefixed by "(bootloader) \t"
        for line in stderr.splitlines():
            if line.startswith("(bootloader) \t"):
                tablines = line.split("\t", 1)
                if len(tablines) > 1:
                    var_array = tablines[1].split(": ", 1)
                    if len(var_array) > 1:
                        variable_name = var_array[0]
                        variable_value = var_array[1]
                        device_info[variable_name] = variable_value

        return device_info

    def is_unlocked(self):
        # Loop until we successfully read all parameters
        while True:
            try:
                var_unlocked = self.getvar('unlocked', use_exception=True)
                break
            except FastbootCommandException:
                pass
        while True:
            try:
                var_secure = self.getvar('secure', use_exception=True)
                break
            except FastbootCommandException:
                pass

        #
        # CAUTION CAUTION CAUTION
        #
        # DO NOT READ lock_state unless necessary!  Some devices (most notably
        # the Nexus 6) return a shell error code for non-standard fastboot
        # variables, which would cause this script to hang.
        #
        # $ fastboot getvar lock_state
        # (bootloader) lock_state: not found
        # getvar:lock_state FAILED (remote failure)
        # $ echo $?
        # 1
        var_lock_state = None
        if self.getvar_product() in ['flo', 'deb']:
            while True:
                try:
                    var_lock_state = self.getvar('lock_state', use_exception=True)
                    break
                except FastbootCommandException:
                    pass

        # Require both unlocked=yes and secure=no
        if var_unlocked == 'yes' and var_secure == 'no':
            return True
        # But print warning when allowing either unlocked=yes or secure=no
        elif var_unlocked == 'yes' or var_secure == 'no':
            self.print_verbose("is_unlocked: Assuming true when unlocked=%s and secure=%s" % \
                               (var_unlocked, var_secure))
            return True
        # If "Lock State" is "unlocked", this should be sufficient
        elif var_lock_state == 'unlocked':
            self.print_verbose("is_unlocked: Assuming true when unlocked=%s, secure=%s, lock_state=%s" % \
                               (var_unlocked, var_secure, var_lock_state))
            return True

        # If 'unlocked' and 'secure' are not sufficient, check the oem device-info
        oem_device_info = self.get_oem_device_info()
        if oem_device_info.get('Device unlocked', 'false') == 'true':
            return True

        return False

    def format(self, partition):
        if self.serial is None:
            cmdline = "fastboot format %s" % partition
        else:
            cmdline = "fastboot -s %s format %s" % (self.serial, partition)

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)

    def wipe(self):
        if self.serial is None:
            cmdline = "fastboot -w"
        else:
            cmdline = "fastboot -s %s -w" % self.serial

        self.print_verbose("Executing: %s" % cmdline)
        command = subprocess.Popen(cmdline,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, stderr = command.communicate()
        if command.returncode != 0:
            self.print_verbose("ReturnCode = %s" % command.returncode)
