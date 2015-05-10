#! /usr/bin/python

from .download_client import DownloadClient

class Firmware(object):
    # TODO: Replace DownloadClient with BlobsCache
    PREFIX = 'https://raw.githubusercontent.com/chub/lma_blobs/firmware/'

    FIRMWARES = {
        'hammerhead' : {
            '5.0' : {
                'bootloader_version' : 'hhz12d',
                'bootloader_file' : PREFIX + 'bootloader-hammerhead-hhz12d.img',
                'radio_version' : 'm8974a-2.0.50.2.21',
                'radio_file' : PREFIX + 'radio-hammerhead-m8974a-2.0.50.2.21.img',
                },
            '5.1' : {
                'bootloader_version' : 'hhz12f',
                'bootloader_file' : PREFIX + 'bootloader-hammerhead-hhz12f.img',
                'radio_version' : 'm8974a-2.0.50.2.25',
                'radio_file' : PREFIX + 'radio-hammerhead-m8974a-2.0.50.2.25.img',
                },
            },
        'mako' : {
            '5.0': {
                'bootloader_version' : 'MAKOZ30f',
                'bootloader_file' : PREFIX + 'bootloader-mako-makoz30f.img',
                'radio_version' : 'm9615a-cefwmazm-2.0.1701.04',
                'radio_file' : PREFIX + 'radio-mako-m9615a-cefwmazm-2.0.1701.04.img',
                },
            '5.1': {
                'bootloader_version' : 'MAKOZ30f',
                'bootloader_file' : PREFIX + 'bootloader-mako-makoz30f.img',
                'radio_version' : 'm9615a-cefwmazm-2.0.1701.06',
                'radio_file' : PREFIX + 'radio-mako-m9615a-cefwmazm-2.0.1701.06.img',
                },
            },
        'flo' : {
            '5.1': {
                'bootloader_version' : 'FLO-04.05',
                'bootloader_file' : PREFIX + 'bootloader-flo-flo-04.05.img',
                },
            },
        # deb
        # grouper
        # tilapia
        # volantis
        # shamu
        # manta
        # 2012-n7-3g
        }

    def __init__(self, adb=None, fastboot=None, device=None,
                 device_info={}, dist=None, download_client=None):
        # Initialize device_name
        self.device_name = None
        if device_info and 'device' in device_info:
            self.device_name = device_info['device']
        # Initialize firmware_ver
        self.firmware_ver = self._get_firmware_version_from_dist(dist)

        self.adb = adb
        self.fastboot = fastboot
        self.device = device

        if download_client is None:
            download_client = DownloadClient()
        self.download_client = download_client

    def _has_suffix(self, source, suffixes):
        for suffix in suffixes:
            if source.endswith(suffix):
                return True
        return False

    def _get_firmware_version_from_dist(self, dist):
        if self._has_suffix(dist, ['cm-11.0']):
            return '4.4'
        elif self._has_suffix(dist, [
            '5.0.2_r1',
            '5.1.0_r1',
            '5.1.0_r3',
            'cm-12.0',
            ]):
            return '5.0'
        elif self._has_suffix(dist, [
            '5.1.1_r1',
            'cm-12.1',
            ]):
            return '5.1'
        return None

    def get_bootloader_version(self):
        if self.device_name not in self.FIRMWARES.keys():
            # Skip firmware version checking for this unknown device
            return None

        mode = self.device.get_mode()
        if mode == 'timedout':
            raise Exception('Unable to verify bootloader version. mode: timedout')
        elif mode == 'fastboot':
            # Assumes Nexus devices
            return self.fastboot.getvar('version-bootloader')
        elif mode in ['recovery', 'device']:
            return self.adb.getprop('ro.boot.bootloader')

        return None

    def get_radio_version(self):
        if self.device_name not in self.FIRMWARES.keys():
            # Skip firmware version checking for this unknown device
            return None

        mode = self.device.get_mode()
        if mode == 'timedout':
            raise Exception('Unable to verify radio version. mode: timedout')
        elif mode == 'fastboot':
            # Assumes Nexus devices
            return self.fastboot.getvar('version-baseband')

        return None

    def has_update(self):
        # Do not process this request if the device type is not known by this class
        if self.device_name not in self.FIRMWARES.keys():
            return False

        # Do not process this request if the firmware version is missing
        if self.firmware_ver not in self.FIRMWARES[self.device_name].keys():
            return False

        bootloader_has_update = False
        radio_has_update = False

        # Get and normalize the proper bootloader version
        proper_bootloader_version = \
            self.FIRMWARES[self.device_name][self.firmware_ver]['bootloader_version']
        if proper_bootloader_version is not None:
            proper_bootloader_version = proper_bootloader_version.lower()

            # Get and normalize the bootloader version currently on the device
            device_bootloader_version = self.get_bootloader_version()
            if device_bootloader_version is not None:
                device_bootloader_version = device_bootloader_version.lower()

                if device_bootloader_version < proper_bootloader_version:
                    print 'Will update bootloader.  Old bootloader: %s.  New bootloader: %s.' % (
                        device_bootloader_version, proper_bootloader_version)
                    bootloader_has_update = True

        # Continue only if a radio is known for this device
        if 'radio_version' in self.FIRMWARES[self.device_name][self.firmware_ver]:
            # Get and normalize the proper radio version.
            proper_radio_version = \
                self.FIRMWARES[self.device_name][self.firmware_ver]['radio_version']
            if proper_radio_version is not None:
                proper_radio_version = proper_radio_version.lower()

                # Get and normalize the radio version currently on the device
                device_radio_version = self.get_radio_version()
                if device_radio_version is not None:
                    device_radio_version = device_radio_version.lower()

                    if device_radio_version < proper_radio_version:
                        print 'Will update radio.  Old radio: %s.  New radio: %s.' % (
                            device_radio_version, proper_radio_version)
                        radio_has_update = True

        return bootloader_has_update or radio_has_update

    def get_bootloader_file(self):
        url = self.FIRMWARES[self.device_name][self.firmware_ver]['bootloader_file']
        return self.download_client.get_local_path(url)

    def get_radio_file(self):
        """
        Radio files do not exist for wifi-only devices.

        This method returns None if there is no radio file for this version.

        This method throws a KeyError during any other case (KeyErrors should be
        consistent with get_bootloader_file()).
        """
        if 'radio_file' in self.FIRMWARES[self.device_name][self.firmware_ver]:
            url = self.FIRMWARES[self.device_name][self.firmware_ver]['radio_file']
            return self.download_client.get_local_path(url)
        else:
            return None
