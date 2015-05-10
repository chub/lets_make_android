from .blobs_cache import BlobsCache

class NoGoogleAppsException(Exception): pass

class GoogleApps(BlobsCache):
    """
    This script assumes the new GApps 2.0
    """

    DEFAULT_FLAVOR = 'FullGApps'

    KITKAT_GAPPS_IMAGE = 'pa_gapps-stock-4.4.4-20141214-signed-keeptmp.zip'
    KITKAT_GAPPS_VERSION = '20141214'

    LOLLIPOP_GAPPS_IMAGE = 'pa_gapps-stock-5.0.1-20150301-signed-keeptmp.zip'
    LOLLIPOP_GAPPS_VERSION = '20150301'

    # 5.1 Gapps is different from 5.0 Gapps
    LOLLIPOP_MR1_GAPPS_IMAGE = 'BaNkS-dynamic-gapps-L-5-3-15-beta2.zip'
    LOLLIPOP_MR1_GAPPS_VERSION = '20150503'

    def __init__(self, flavor=None, device=None, *args, **kwargs):
        super(GoogleApps, self).__init__(*args, **kwargs)

        # GApps only accepts the following flavors.
        if flavor is not None and \
                flavor not in ['FullGApps', 'MiniGApps', 'MicroGApps', 'NanoGApps', 'PicoGApps']:
            raise Exception('Unsupported gapps flavor "%s"' % flavor)

        self.flavor = flavor
        self.device = device

    def get_gapps_zip(self, ota_build=None):
        """
        Returns the path to the stock gapps package for the appropriate CM version
        """
        gapps_image = self.get_gapps_image(ota_build=ota_build)
        if gapps_image.startswith('/'):
            # Assume gapps_image is a local path.
            # This is frequently used to test gapps before uploading to S3.
            return gapps_image
        else:
            # Assume S3 Path
            return self.get_local_path(self.get_gapps_image(ota_build=ota_build))

    def get_gapps_config(self):
        """
        Returns the gapps-config for gapps 2.0 in an list, line by line.
        """
        gapps_config = ['Debug']
        if self.flavor is None:
            # 2012 Nexus 7's need micro
            if self.device in  ['grouper', 'tilapia']:
                gapps_config += [ 'MicroGApps' ]
            # 2013 Nexus 7's only have 414MB free after CM12 flash
            elif self.device in ['flo', 'deb']:
                # FullGApps was rejected
                gapps_config += [ 'MiniGApps' ]
            # Nexus 4's only have 391M free after CM12 flash
            elif self.device in ['mako']:
                gapps_config += [ 'MiniGApps' ]
            # Use stock for all other Nexus devices
            elif self.device in [
                    'mako', # Nexus 4
                    'manta', # Nexus 10
                    'hammerhead', # Nexus 5
                    'shamu', # Nexus 6
                    'fugu', # Nexus Player
                    'voltanis', # Nexus 9
                ]:
                # Flavor restriction not needed for full stock
                pass
            else:
                # All other devices should use full
                # Note: bacon needs full since Camera from CM is better
                gapps_config += [ self.DEFAULT_FLAVOR ]
        else:
            gapps_config += [ self.flavor ]

        return gapps_config

    @classmethod
    def get_gapps_image(cls, ota_build=None):
        if ota_build is not None:
            cm_base = ota_build.get_base_cm_filename()
            if cm_base is not None:
                if cm_base.startswith('11-'):
                    return cls.KITKAT_GAPPS_IMAGE
                elif cm_base.startswith('12-'):
                    return cls.LOLLIPOP_GAPPS_IMAGE

            aosp_version = ota_build.get_aosp_version()
            if aosp_version is not None:
                if aosp_version.startswith('4.'):
                    return cls.KITKAT_GAPPS_IMAGE
                elif aosp_version.startswith('5.1'):
                    return cls.LOLLIPOP_MR1_GAPPS_IMAGE
                elif aosp_version.startswith('5.'):
                    return cls.LOLLIPOP_GAPPS_IMAGE

        raise Exception('Could not determine which gapps to use for ROM %s' % ota_build)

    @classmethod
    def get_gapps_version(cls, ota_build=None):
        if ota_build is not None:
            cm_base = ota_build.get_base_cm_filename()
            if cm_base is not None:
                if cm_base.startswith('11-'):
                    return cls.KITKAT_GAPPS_VERSION
                elif cm_base.startswith('12-'):
                    return cls.LOLLIPOP_GAPPS_VERSION

            aosp_version = ota_build.get_aosp_version()
            if aosp_version is not None:
                if aosp_version.startswith('4.'):
                    return cls.KITKAT_GAPPS_VERSION
                elif aosp_version.startswith('5.1'):
                    return cls.LOLLIPOP_MR1_GAPPS_IMAGE
                elif aosp_version.startswith('5.'):
                    return cls.LOLLIPOP_GAPPS_VERSION

        raise Exception('Could not determine which gapps to use for ROM %s' % ota_build)

    @classmethod
    def is_upgrade_available(cls, adb=None, ota_build=None):
        """
        Determines whether gapps on the system is older than the one the script knows about.

        We are standardizing on PA's GApps' distribution, which uses datestamps as their version.

        If an upgrade is available, return a tuple: (old_version, new_version).
        Otherwise, return None.
        """
        adb.shell('mount /system')
        device_gapps_version = adb.getprop_file('ro.addon.pa_version',
                                                prop_file='/system/etc/g.prop')
        script_gapps_version = cls.get_gapps_version(ota_build=ota_build)

        upgrade_available = False

        # Compare the gapps versions
        if device_gapps_version is None or device_gapps_version == '':
            device_gapps_version = "''"
            upgrade_available = True
        else:
            try:
                if int(device_gapps_version) < int(script_gapps_version):
                    upgrade_available = True
            except ValueError:
                if device_gapps_version < script_gapps_version:
                    upgrade_available = True

        if upgrade_available:
            return (device_gapps_version, script_gapps_version)

        # No upgrade available
        return None
