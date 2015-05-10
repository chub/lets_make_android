#! /usr/bin/python

import sys
import time

# From parent package
from wrapper.open_recovery_script import OpenRecoveryScript

from .colorcli import ColorCli
from .cm_rom import CmRom
from .firmware import Firmware
from .google_apps import GoogleApps, NoGoogleAppsException
from .recovery import Recovery
from .sideloadable_ota_build import SideloadableOtaBuild
from .supersu import SuperSU

class FlashHelper(object):
    def __init__(self, adb=None, device=None, fastboot=None):
        self.adb = adb
        self.device = device
        self.fastboot = fastboot
        self.userdata_wiped = False

    def set_userdata_wiped(self):
        self.userdata_wiped = True

    def get_cm_version(self):
        """
        Returns the fully-qualified CM version (CM-11-YYYYMMDD-...) defined by /system.

        This can be used to detect if CM is installed on the device.  If the string is
        empty, CM may not be installed.

        Note: This reads and parses /system/build.prop since "getprop" does not read the
        /system/build.prop file in recovery.
        """
        # Valid modes include device and recovery modes.
        mode = self.device.get_mode()
        if mode == 'timedout':
            raise Exception('Unable to verify CM installation. mode: timedout')
        elif mode not in ['recovery', 'device']:
            self.device.reboot_to_recovery()

        # /system is already mounted in device mode
        if mode == 'recovery':
            mount_cmd = self.adb.shell('mount /system')

        return self.adb.getprop_system('ro.cm.display.version')

    def get_aosp_version(self):
        """
        Returns the ro.build.version.release string defined by /system.

        This can be used to detect if AOSP is installed on the device.  If the string is
        empty, AOSP may not be installed.

        Note: This reads and parses /system/build.prop since "getprop" does not read the
        /system/build.prop file in recovery.
        """
        # Valid modes include device and recovery modes.
        mode = self.device.get_mode()
        if mode == 'timedout':
            raise Exception('Unable to verify CM installation. mode: timedout')
        elif mode not in ['recovery', 'device']:
            self.device.reboot_to_recovery()

        # /system is already mounted in device mode
        if mode == 'recovery':
            mount_cmd = self.adb.shell('mount /system')

        return self.adb.getprop_system('ro.build.version.release')

    def get_device_system_build_fingerprint(self):
        """
        Returns the framework code and the fingerprint of the current
        installation on the device.

        The ROM code is "AOSP" or "cyanogenmod".  This indicates whether we are
        switching Android frameworks.

        This fingerprint should not be parsed and is different for every build.  If the
        fingerprint differs from the indicated build, a --full will be needed.

        Note: The fingerprint is NOT the same as the system version (CM 11 vs
        AOSP 5.1). See get_cm_version() and get_aosp_version().

        Returns ('cyanogenmod', the ro.cm.display.version string defined by /system) if CM is installed.
        Returns ('aosp', the ro.build.display.id string) if AOSP is installed.
        Returns (None, None) if no OS was found.
        """
        # Valid modes include device and recovery modes.
        mode = self.device.get_mode()
        if mode == 'timedout':
            raise Exception('Unable to verify CM installation. mode: timedout')
        elif mode not in ['recovery', 'device']:
            self.device.reboot_to_recovery()

        # /system is already mounted in device mode
        if mode == 'recovery':
            mount_cmd = self.adb.shell('mount /system')

        framework_code = None
        fingerprint = None
        if self.adb.path_exists('/data/system/packages.xml'):
            framework_code = 'cyanogenmod'
            fingerprint = self.adb.getprop_system('ro.cm.display.version')

            if fingerprint in [None, '']:
                framework_code = 'aosp'
                fingerprint = self.adb.getprop_system('ro.build.display.id')

        return (framework_code, fingerprint)

    def get_ota_build_fingerprint(self, ota_build=None):
        """
        Returns the framework code and the fingerprint of the OTA.

        To be used in conjunction with get_device_system_build_fingerprint().
        """
        framework_code = None
        fingerprint = None
        if ota_build is not None:
            framework_code = 'cyanogenmod'
            fingerprint = ota_build.get_base_cm_filename()

            if fingerprint in [None, '']:
                framework_code = 'aosp'
                fingerprint = ota_build.getprop_system('ro.build.display.id')

        return (framework_code, fingerprint)

    def is_twrp(self):
        """
        Returns true if the recovery running is TWRP.  False otherwise.
        """
        mode = self.device.get_mode()
        if mode == 'timedout':
            raise Exception('Unable to verify TWRP recovery. mode: timedout')
        elif mode not in ['recovery']:
            self.device.reboot_to_recovery()
            # Wait for recovery before proceeding
            #
            # Note: Do not depend on the /cache directory.  If something is
            # wrong with the partition table, /cache, /data, and /system
            # partitions may never get mounted.
            self.adb.wait_for_path_or_mount(path='/tmp/recovery.log', debounce=3)

        # getprop may fail if the device is still rebooting.
        try:
            which_twrp_cmd = self.adb.shell('which twrp')
            which_twrp = which_twrp_cmd.stdout.strip()
        except:
            which_twrp = ''
        return which_twrp != ''

    def flash_firmware(self, first=False, device_info={}, dist=None):
        firmware = Firmware(device_info=device_info,
                            dist=dist,
                            adb=self.adb,
                            fastboot=self.fastboot,
                            device=self.device)

        # If --first is passed, then automatically flash firmware
        replace_firmware = first

        # If we are not authorized to flash firmware, check if firmware is out of date.
        if not replace_firmware:
            if firmware.has_update():
                replace_firmware = True

        # Only continue flashing the firmware if there is a update.
        if replace_firmware:
            # Download bootloader and radio
            bootloader = firmware.get_bootloader_file()
            radio = firmware.get_radio_file()

            self.device.reboot_to_fastboot()
            self.fastboot.flash('bootloader', bootloader)
            self.device.reboot_to_fastboot(forced=True)

            if radio:
                self.fastboot.flash('radio', radio)
                self.device.reboot_to_fastboot(forced=True)

    def flash_compatible_recovery(self, first=False, device_info={}):
        """
        Ensure device receives a compatible recovery.  Handle all device states.
        """
        # If --first is passed, then we flash recovery
        flash_needed = first

        # Otherwise, only flash recovery if twrp is not installed
        if not flash_needed:
            if not self.is_twrp():
                print 'TWRP not detected. Going to bootloader mode to flash TWRP into recovery.'
                flash_needed = True

        # If flash_needed is true, continue
        if flash_needed:
            recoveryfile = Recovery().get_recovery(device_info['device'])

            # Reboot into bootloader mode
            self.device.reboot_to_fastboot()

            # if --first, also format system and userdata to start from scratch
            if first:
                self.fastboot.format('system')
                self.fastboot.wipe()
                self.set_userdata_wiped()

            # Install recovery image
            self.fastboot.flash('recovery', recoveryfile)

            # Boot to new recovery image (but do not flash recovery)
            self.fastboot.boot(recoveryfile, just_flashed_recovery=True)

    def prepare_partitions(self, flags=None, count=0):
        """
        Asserts that /data and /sdcard are both mounted in fewer than 3 restarts.

        The recovery used must make incremental progress, or else the method will time out.

        1. If both /data and /sdcard are not mounted, then data needs to be wiped (checks --wipe).
        2. If /data is mounted but /sdcard is not mounted, then TWRP needs to be restarted.
        3. Checks if /data and /sdcard are both mounted.  If not, throws an error (it should not
           have taken that long).

        Note: If this methods encounters any other cases (either completely different cases, or
        something out of order), then the device is in unexcepted case and the script will halt.

        Returns whether the partitions have been prepared.
        """
        # Wait for TWRP to start. Do not depend on /cache being available (after all, /cache is
        # tied to fastboot -w).
        self.adb.wait_for_path_or_mount(path='/tmp/recovery.log', debounce=3)

        # Observe device partition state.
        is_data_mounted = self.adb.is_mount_point_mounted(mount='/data')
        is_sdcard_mounted = self.adb.is_mount_point_mounted(mount='/sdcard')
        if is_data_mounted and is_sdcard_mounted:
            # We're done here. Nothing to do.
            return True

        if not is_data_mounted and not is_sdcard_mounted:
            # This is most commonly the case where a device was just unlocked and had its
            # userdata partition erased (but not formatted).  If --first or --wipe was passed,
            # then go into bootloader mode and wipe it.  A verbose explanation follows:
            #
            # Turns out this is one massive regression+bug from ClockworkMod Recovery days.
            #
            # When a device is unlocked, the bootloader can set the following Boot Control Block
            # in the /misc partition to signal the recovery image:
            #
            #    struct bootloader_message {
            #        char command[32] = "boot-recovery";
            #        char status[32]; // whatever
            #        char recovery[1024] = "recovery\n--wipe_data";
            #    };
            # If the device runs a standard recovery like TWRP and stock Android recovery, it would:
            # - read the BCB from /misc and parse bootloader_message.recovery,
            # - wipe the userdata (and cache, optionally),
            # - clear the command and recovery fields of the bootloader_message struct and write it
            #   back to /misc, and
            # - continue booting to device mode.
            #
            # If you are CWM Recovery, you do everything except for the last step.  In our case, we
            # actually do NOT want the recovery to boot into device mode. If it does, the system
            # will hang until adb is enabled.
            # The proper fix is two-fold:
            # - detect when certain partitions are missing (but are expected to be there); and
            # - when --first is passed, take a trip through CWMR so the BCB can be safely cleared,
            #   and continue on with TWRP.
            if not flags.first and not flags.wipe:
                # Ask for --wipe permission and halt.
                ColorCli.print_red('/data partition does not appear to be formatted.')
                ColorCli.print_red('If you would like to continue, please re-execute with --wipe.')
                sys.exit(1)

            # Go to bootloader mode and wipe.
            if flags.verbose:
                print '\tprepare_partitions: stage A, wiping user data.'
            self.device.reboot_to_fastboot()
            self.fastboot.wipe()
            self.set_userdata_wiped()
            self.device.reboot_to_recovery()
            # Wait for the device to come back

        is_data_mounted = self.adb.is_mount_point_mounted(mount='/data')
        is_sdcard_mounted = self.adb.is_mount_point_mounted(mount='/sdcard')
        if not is_data_mounted:
            if flags.verbose:
                print '\tprepare_partitions: stage B, /data is not mounted.  This is unexpected.'
            ColorCli.print_red('/data should be mounted by now, but it is not. Please report a bug.')
            sys.exit(1)

        if not is_sdcard_mounted:
            # Welp, sometimes /data needs a massaging.
            # This is necessary for TWRP v2.8.6.0 and higher (especially after a --first).
            self.adb.shell('mkdir -p /data/media')

            # reboot and wait for it.
            if flags.verbose:
                print '\tprepare_partitions: stage B, /data is mounted but need to reboot to get /sdcard mounted'

            self.device.reboot_to_recovery(forced=True)

        is_data_mounted = self.adb.is_mount_point_mounted(mount='/data')
        is_sdcard_mounted = self.adb.is_mount_point_mounted(mount='/sdcard')
        if not is_data_mounted or not is_sdcard_mounted:
            # Now we really need help.
            if flags.verbose:
                print '\tprepare_partitions: stage C, /data is not mounted or /sdcard is not mounted. Check /etc/mtab'
            ColorCli.print_red('Both /data and /sdcard should be mounted by now, but they are not. Please report a bug.')
            sys.exit(1)

    def is_releasekey_different(self):
        """
        If this is a --full flash, check if openrecovery script is halted by otasigcheck.sh.
        Detect by observing /tmp/releasekey for the canary value.
        If so, instruct user about --wipe switch to continue.

        Returns true if /data cannot be mounted for some reason (necessitating a wipe).
        Returns true if an invalid releasekey is detected and flashing halted.
        Returns false if the flash is expected to complete.
        """
        self.adb.wait_for_recovery()

        # Assume we can check /data now
        if not self.adb.is_mount_point_mounted(mount='/data'):
            return False

        # Wait for file to be created first.
        self.adb.wait_for_path_or_mount(path='/tmp/releasekey', mount='/data', debounce=2)

        # Then wait for file contents to stablize.
        count = 0
        last_sha1sum = None
        while True:
            if count > 3:
                break

            sha1sum_cmd = self.adb.shell('sha1sum /tmp/releasekey')
            sha1sum = sha1sum_cmd.stdout.strip()
            if len(sha1sum) > 1:
                if last_sha1sum is None or last_sha1sum != sha1sum:
                    count = 1
                    last_sha1sum = sha1sum
                else:
                    count = count + 1

            time.sleep(1)

        # Check if the sha1sum is of INVALID
        # $ adb shell sha1sum /tmp/releasekey
        # 7241e92725436afc79389d4fc2333a2aa8c20230  /tmp/releasekey
        if sha1sum.startswith('7241e92725436afc79389d4fc2333a2aa8c20230'):
            return True

        return False

    @classmethod
    def add_common_arguments(cls, parser=None):
        """
        Specifies common arguments.
        """
        parser.add_argument('--full',
                            action='store_true',
                            help='reinstalls CyanogenMod on device')
        parser.add_argument('--wipe',
                            action='store_true',
                            help='wipes userdata')
        gapps_group = parser.add_mutually_exclusive_group()
        gapps_group.add_argument('--gapps',
                                 nargs='?',
                                 const='__', # If --gapps lacks a value, sub '__' as the value.
                                 help='installs and upgrades gapps')
        gapps_group.add_argument('--no_gapps',
                                 action='store_true',
                                 help='do not install or upgrade gapps')
        parser.add_argument('--device', type=str,
                            help='specifies device type')
        parser.add_argument('--dist', type=str,
                            default='android-5.1.1_r1',
                            help='specifies distribution')
        parser.add_argument('--first',
                            action='store_true',
                            help='use this when the device is running stock recovery (useful for brand new devices)')
        parser.add_argument('--skip_installs',
                            action='store_false',
                            help='skips installing sideload or system_apps')
        parser.add_argument('--verbose',
                            default=True,
                            action='store_true',
                            help='increases verbosity')
        return parser


    def perform_template_flash(self, flags=None, device_info=None,
                               install_zip=None,
                               install_system_app_apk=None,
                               ota_build=None, # Represents a full or delta OTA, if it is included.
                               full_rom=None):
        """
        A templated flash follows these steps:
        - Check if there is a newer firmware (baseband and radio)
        - Check if compatible recovery is installed (skip if --first)
        - Optinally install compatible recovery
        - Check if OS and gapps needs to be installed first
        - Optionally install OS
        - Optionally install gapps
        - Install sideload or APK (unless --skip_installs is true)
        """
        # Print what's about to happen
        print 'flash instructions:'
        print '  dist:          %s' % flags.dist
        print '  device name:   %s' % device_info['device']
        print '  device serial: %s' % device_info['serial']
        print '-----------------'
        # Check if the firmware needs updating.
        self.flash_firmware(device_info=device_info, dist=flags.dist)

        # Check if the recovery image is twrp.  Flash TWRP if not.
        self.flash_compatible_recovery(first=flags.first, device_info=device_info)

        self.prepare_partitions(flags=flags)

        # Check if device needs to have its system flashed. If so, --full is forced on.
        if not flags.full:
            current_framework, current_fingerprint = self.get_device_system_build_fingerprint()
            if current_framework in [None, ''] or current_fingerprint in [None, '']:
                # We will automatically continue if:
                # 1. --first is passed,
                # 2. --wipe is passed, or
                # 3. /data is semantically empty (after a fastboot wipe)
                if flags.first or flags.wipe or not self.adb.path_exists('/data/system/packages.xml'):
                    # Toggle --full --gapps on
                    # --wipe can be toggled in case 3 only (but not in cases 1 and 2).
                    if not flags.first and not flags.wipe and not self.adb.path_exists('/data/system/packages.xml'):
                        print 'Android was not found, and /data already looks empty.  Assuming --full --gapps --wipe'
                        flags.wipe = True
                    else:
                        if flags.no_gapps:
                            print 'Android was not found.  Assuming --full'
                            flags.full = True
                        else:
                            print 'Android was not found.  Assuming --full --gapps'
                            flags.full = True
                            flags.gapps = '__'
                else:
                    ColorCli.print_red('Android was not found.')
                    ColorCli.print_red('Note: For this script to continue, userdata must also be wiped.')
                    ColorCli.print_red('To continue, please re-execute this script with --wipe.')
                    sys.exit(1)
            else:
                ota_framework, ota_fingerprint = self.get_ota_build_fingerprint(ota_build=ota_build)

                # Bail if the version of Android in the OTA is unknown.
                if ota_framework is None:
                    if ota_build is None:
                        ColorCli.print_red('Unsupported OTA build: ota_build is None')
                    else:
                        ColorCli.print_red('Unsupported OTA build.  ota_framework is None, ota_fingerprint is "%r"' % ota_fingerprint)
                        ColorCli.print_red('Check contents of %s' % ota_build.find_s3_path())
                    ColorCli.print_red('Exiting.  System not modified.')
                    sys.exit(1)

                # Bail if the Android OS in the OTA is different from the Android OS in the device (CM vs AOSP, for example).
                elif ota_framework != current_framework:
                    ColorCli.print_red('Unexpected Android installation found.  Expected %s, found %s.' % (ota_framework, current_framework))
                    ColorCli.print_red('')
                    ColorCli.print_red('The device will need to be fully flashed and wiped.  Please re-execute with --full --wipe.')
                    sys.exit(1)

                # Test if the device needs upgrading.
                elif ota_fingerprint != current_fingerprint:
                    # This is a device that is running a different version of Android.

                    # Determine whether gapps upgrades are disabled (this affects the printout).
                    if not flags.wipe:
                        flags.wipe = False
                        if not flags.gapps:
                            # Check if --no_gapps was passed.
                            if not flags.no_gapps:
                                flags.gapps = '__'
                    assumed_gapps_flag = ' --gapps' if flags.gapps == '__' else ''

                    # Do not wipe! Just overlay
                    print 'Upgrade found for this Android installation. Assuming --full' + assumed_gapps_flag
                    print '  Old: %s' % current_fingerprint
                    print '  New: %s' % ota_fingerprint
                    flags.full = True

        # Check if the device needs to update gapps. If so, --gapps is forced on.
        if not flags.gapps:
            upgrade_details = None
            try:
                upgrade_details = GoogleApps.is_upgrade_available(adb=self.adb,
                                                                  ota_build=ota_build)
            except NoGoogleAppsException, e:
                ColorCli.print_red('Skipping GApps: "%s"' % e.message)

            if upgrade_details is not None:
                # We have a Gapps update for this device.
                old_gapps_version, new_gapps_version = upgrade_details
                if flags.no_gapps:
                    # But gapps updating is disabled. =(
                    print 'Note: Older gapps detected (%s).  Newer gapps is available (%s) but will not be installed.' % (old_gapps_version, new_gapps_version)
                else:
                    print 'Newer gapps available.  Assuming --gapps to upgrade from %s to %s.' % (old_gapps_version, new_gapps_version)
                    flags.gapps = '__'

        # Create OpenRecoveryScript
        script = OpenRecoveryScript(serial=device_info['serial'], verbose=flags.verbose)

        # Erase userdata if requested and if not already wiped.
        # Note: For bacon, userdata must be first wiped before CM will install
        #       As a result, wipe_userdata now occurs before sideloading zip
        if flags.wipe and not self.userdata_wiped:
            script.wipe_userdata()
            self.set_userdata_wiped()

        # If --full, install CM
        if flags.full:
            if full_rom is None:
                ColorCli.print_red('--full was specified, but no Full ROM was found.')
                sys.exit(1)

            # TODO: Unify the interface between SideloadableOtaBuild and CmRom
            if type(full_rom) == SideloadableOtaBuild:
                cm_zip_file = full_rom.get_local_path()
            else:
                cm_zip_file = full_rom.get_zip()
            script.install_zip(cm_zip_file)

            # Install SuperSU
            supersu = SuperSU()
            script.install_zip(supersu.get_supersu_zip())

        # If --gapps, install Gapps
        # Also, the required CM version is needed to load the proper gapps (kitkat vs. lollipop)
        if flags.gapps is not None:
            flavor = flags.gapps
            if flavor == '__':
                flavor = None
                google_apps = GoogleApps(flavor=flavor, device=device_info['device'])

                gapps_zip_file = google_apps.get_gapps_zip(ota_build=ota_build)
                script.install_zip(gapps_zip_file)

                # Install gapps-config
                self.adb.shell('echo -n > %s/.gapps-config' % OpenRecoveryScript.ZIP_PREFIX)
                for line in google_apps.get_gapps_config():
                    self.adb.shell('echo %s >> %s/.gapps-config' % (line, OpenRecoveryScript.ZIP_PREFIX))

        # Install sideloads and APK last
        if not flags.skip_installs:
            # This is an OTA install
            if install_zip:
                script.install_zip(install_zip)
            # This is an single APK install
            if install_system_app_apk:
                script.install_file(install_system_app_apk, '/system/app/')

        # After the script executes, restart into system mode
        script.reboot_to('system')

        # Execute script on device
        script.execute()

        # If userdata was not already wiped, then check if the user needs to wipe data.
        if not self.userdata_wiped:
            if flags.full and self.is_releasekey_different():
                ColorCli.print_red('Script FAILED.  Flash could not complete.')
                ColorCli.print_red('userdata must be wiped.')
                ColorCli.print_red('If you would like to continue, please re-execute with --wipe.')
                sys.exit(1)

        # We are done
        ColorCli.print_green('Done!')
