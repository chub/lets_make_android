import os
import subprocess
from zipfile import ZipFile

class BuildPropCommon(object):
    """
    build.prop common behaviors.

    Currently can be used with:
    - SideloadableOtaBuilds zips
    - CmRom zips
    """
    BUILD_PROP_LOCATION = 'system/build.prop'

    CM_BASE_PROP_1 = 'ro.cm.display.version'
    CM_BASE_PROP_2 = 'ro.modversion'

    AOSP_VERSION_PROP_1 = 'ro.build.version.release'

    def __init__(self, local_path_to_zip):
        self.local_path_to_zip = local_path_to_zip
        self.cached_build_props = None

    def _parse_build_props(self):
        if self.cached_build_props is not None:
            return self.cached_build_props

        self.cached_build_props = {}

        # Read in build_props
        with ZipFile(self.local_path_to_zip, 'r') as zipfile_h:
            build_props = zipfile_h.read(self.BUILD_PROP_LOCATION)

        for prop_line in build_props.splitlines():
            # Skip comments and any line that isn't a key-value pair
            if prop_line.startswith('#'):
                continue
            if '=' not in prop_line:
                continue

            prop_name, prop_val = prop_line.split('=', 1)
            if prop_name in self.cached_build_props and \
                    prop_val != self.cached_build_props[prop_name]:
                print 'WARN: Duplicate property "%s" has two values ("%s", "%s")' % \
                    (prop_name, self.cached_build_props[prop_name], prop_val)
            self.cached_build_props[prop_name] = prop_val

        return self.cached_build_props

    def get_prop(self, prop=None, props=None):
        """
        Returns the value of the first property that is found.

        If the argument is a string, than only one property will be searched.
        """
        if prop is not None and props is not None:
            raise Exception('get_prop only accepts either prop (%r) or props (%r), but not both' % (prop, props))

        if prop is not None:
            props = [prop]

        build_props = self._parse_build_props()
        for i_prop in props:
            if i_prop in build_props:
                return build_props[i_prop]

        return None

    def get_base_cm_filename(self):
        """
        Returns the CM build needed to install a ROM-tagged sideload.

        Examines the included build.prop from the sideload zip and searches for either:
        - ro.modversion=11-20140504-SNAPSHOT-M6-hammerhead or
        - ro.cm.display.version=11-20140504-SNAPSHOT-M6-hammerhead

        Historically, ro.cm.version is the prop to use, but ROM-tagged sideloads overwrites this.
        """
        return self.get_prop(props=[self.CM_BASE_PROP_1, self.CM_BASE_PROP_2])

    def get_aosp_version(self):
        """
        Returns the major.minor version of Android for an AOSP ZIP.
        """
        return self.get_prop(prop=self.AOSP_VERSION_PROP_1)
