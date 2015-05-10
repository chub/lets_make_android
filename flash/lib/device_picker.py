class DevicePicker(object):
    @classmethod
    def pick(cls, device_hint=None, interactive=True):
        return cls().choose_device(device_hint=device_hint)

    def translate_adb_device(self, device=None, product=None):
        """
        Handles inconsistent product/device attributes.

        Since product is deprecated, trust device by default.  Create exceptions to this rule here.

        bacon:
        $serial       device usb:14112000 product:bacon model:One device:A0001
        hammerhead:
        $serial       device usb:FA131000 product:hammerhead model:Nexus_5 device:hammerhead
        condor:
        $serial       device usb:14112000 product:cm_condor model:XT1023 device:condor_umts
        """
        if product == 'bacon' and device == 'A0001':
            return 'bacon'
        elif device == 'condor_utms':
            return 'condor'
        else:
            return device

    def choose_device(self, device_hint=None, interactive=True):
        """
        Selects first device, or prompts user (if interactive).
        """
        device_list = self.list_devices()

        # Save original list length so a nicer message may be displayed to user.
        orig_list_len = len(device_list)
        if device_hint:
            # Filter device by device_hint.  Must be exact match.
            device_list = [ item for item in device_list if device_hint == item['device'] ]

        if len(device_list) > 1 and interactive:
            while True:
                print "Select one of the following devices:"

                count = 1
                for device in device_list:
                    print '%d: %s\t%s' % (count, device['serial'], device['device'])
                    count += 1

                options = "".join([ str(x) for x in xrange(1, 1+len(device_list)) ])
                index_str = raw_input('Select a device[%s]: ' % options)
                index_int = None
                try:
                    index_int = int(index_str)-1
                except ValueError:
                    pass

                if index_int is not None and \
                   int(index_int) < len(device_list):
                    return device_list[index_int]

                print 'Invalid response "%s"' % index_str
                print ''
        elif len(device_list) > 1 and not interactive:
            raise Exception('Cannot auto-choose among %d devices.  If scripted, consider ANDROID_SERIAL.',
                            len(device_list))
        elif len(device_list) == 1:
            return device_list[0]
        elif len(device_list) == 0 and orig_list_len > 0 and device_hint:
            raise Exception('device_hint "%s" does not match any connected devices.' % device_hint)
        else:
            raise Exception('Did not detect any connected devices.')

    def list_devices_adb(self):
        """
        Returns a list of device dictionaries, or an empty list.
        Dictionaries all have both the 'serial' key and the 'model' key.
        """
        # Run 'adb devices -l' in a sub-shell, capturing stdout and stderr.
        devicescmd = subprocess.Popen("adb devices -l", shell = True,
                                      stdout = subprocess.PIPE)
        output, errout = devicescmd.communicate()
        if devicescmd.returncode != 0:
            print("Failed to list devices via adb: {}".format(errout))
            return list()

        accumulator = list()

        # Parse serial and model name.
        # First, skip until the line "List of devices attached" is found
        is_adb_header = True
        for line in output.split("\n"):
            if is_adb_header:
                # If is_adb_header is not yet false, keep searching for our escape line
                if line.startswith("List of devices attached"):
                    is_adb_header = False
                continue

            # Split the line into components based on whitespace.
            components = line.split()

            if len(components) >= 5 and 'device:' in components[5]:
                # Product is deprecated but sometimes contains correct information
                device = components[5].split(":")[1]
                product = None
                if 'product:' in components[3]:
                    product = components[3].split(":")[1]
                translated_device = self.translate_adb_device(device=device, product=product)

                accumulator.append({'serial': components[0],
                                    'device': translated_device})

            # List unauthorized devices too.
            if len(components) >= 2 and (
                    components[1] == 'unauthorized' or
                    components[1] == 'offline'):
                accumulator.append({'serial': components[0],
                                    'device': 'unauthorized'})

        return accumulator

    def list_devices_fastboot(self):
        devices = list()
        devicescmd = subprocess.Popen(
            'fastboot devices -l', shell=True, stdout=subprocess.PIPE)
        output, errout = devicescmd.communicate()
        if devicescmd.returncode != 0:
            print("Failed to list devices via fastboot: {}".format(errout))
            return devices

        for line in output.split("\n"):
            components = line.split()
            if len(components) > 0:
                serial = components[0]
                product = Fastboot(serial=serial).getvar_product()
                devices.append({'serial': serial,
                                'device': product})

        return devices

    def list_devices(self):
        devices = list()
        devices.extend(self.list_devices_adb())
        devices.extend(self.list_devices_fastboot())
        return devices

    @classmethod
    def check_device_authorization(cls, device_info):
        if device_info['device'] == 'unauthorized':
            raise Exception('Device has adb locked. Please accept the adb connection from the device.')
