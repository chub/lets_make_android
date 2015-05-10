#! /usr/bin/python

import argparse

from lib.build_set import BuildSet
from lib.cm_rom import CmRom
from lib.device_picker import DevicePicker
from lib.flash_helper import FlashHelper

from wrapper.adb import AdbSerial
from wrapper.device import Device
from wrapper.fastboot import Fastboot

if __name__ == '__main__':
    parser = FlashHelper.add_common_arguments(parser=argparse.ArgumentParser())
    parser.add_argument('--pipeline_number',
                        type=int,
                        help='specify the pipeline number to build')
    flags = parser.parse_args()

    # May be interactive
    device_info = DevicePicker.pick(device_hint=flags.device)
    DevicePicker.check_device_authorization(device_info)

    # Instantiate
    adb = AdbSerial(serial=device_info['serial'], verbose=flags.verbose)
    device = Device(serial=device_info['serial'], verbose=flags.verbose)
    fastboot = Fastboot(serial=device_info['serial'], verbose=flags.verbose)
    flash_helper = FlashHelper(adb=adb, device=device, fastboot=fastboot)

    # Find the appropriate build set
    build_set = BuildSet(device=device_info['device'],
                         dist=flags.dist,
                         pipeline_number=flags.pipeline_number)

    if build_set.type == BuildSet.TYPE_DELTA_OTA:
        # Delta OTAs require a full ROM.
        # For now, only CM Milestones are supported.
        delta_ota_zip = build_set.ota_build.get_local_path()

        # Check for the latest version of the CM Milestone
        cm_rom = CmRom(device_info['device'],
                       cm_filename=build_set.ota_build.get_base_cm_filename())

        flash_helper.perform_template_flash(
            flags = flags,
            device_info = device_info,
            install_zip = delta_ota_zip,
            ota_build = build_set.ota_build,
            full_rom = cm_rom)
    elif build_set.type == BuildSet.TYPE_FULL_OTA:
        flash_helper.perform_template_flash(
            flags = flags,
            device_info = device_info,
            ota_build = build_set.ota_build,
            full_rom = build_set.ota_build)
