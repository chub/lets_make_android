#!/usr/bin/env python
#
# Copyright (C) 2008 The Android Open Source Project
# Copyright (C) 2014 github.com/chub
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Given a target-files zipfile, produces an OTA package that installs
that build.  An incremental OTA is produced if -i is given, otherwise
a full OTA is produced.

Usage:  ota_from_target_files [flags] input_target_files output_ota_package

  -b  (--board_config)  <file>
      Deprecated.

  -k (--package_key) <key> Key to use to sign the package (default is
      the value of default_system_dev_certificate from the input
      target-files's META/misc_info.txt, or
      "build/target/product/security/testkey" if that value is not
      specified).

      For incremental OTAs, the default value is based on the source
      target-file, not the target build.

  -i  (--incremental_from)  <file>
      Generate an incremental OTA using the given target-files zip as
      the starting build.

  -w  (--wipe_user_data)
      Generate an OTA package that will wipe the user data partition
      when installed.

  -n  (--no_prereq)
      Omit the timestamp prereq check normally included at the top of
      the build scripts (used for developer OTA packages which
      legitimately need to go back and forth).

  -e  (--extra_script)  <file>
      Insert the contents of file at the end of the update script.

  -a  (--aslr_mode)  <on|off>
      Specify whether to turn on ASLR for the package (on by default).

  --backup <boolean>
      Enable or disable the execution of backuptool.sh.
      Disabled by default.

  --override_device <device>
      Override device-specific asserts. Can be a comma-separated list.

  --override_prop <boolean>
      Override build.prop items with custom vendor init.
      Enabled when TARGET_UNIFIED_DEVICE is defined in BoardConfig

"""

import sys

if sys.hexversion < 0x02040000:
  print >> sys.stderr, "Python 2.4 or newer is required."
  sys.exit(1)

import copy
import errno
import os
import re
import subprocess
import tempfile
import time
import zipfile

try:
  from hashlib import sha1 as sha1
except ImportError:
  from sha import sha as sha1

import common
import edify_generator

OPTIONS = common.OPTIONS
OPTIONS.package_key = None
OPTIONS.incremental_source = None
OPTIONS.require_verbatim = set()
OPTIONS.prohibit_verbatim = set(("system/build.prop",))
OPTIONS.patch_threshold = 0.95
OPTIONS.wipe_user_data = False
OPTIONS.omit_prereq = False
OPTIONS.extra_script = None
OPTIONS.aslr_mode = True
OPTIONS.worker_threads = 3
OPTIONS.backuptool = False
OPTIONS.override_device = 'auto'
OPTIONS.override_prop = False

def MostPopularKey(d, default):
  """Given a dict, return the key corresponding to the largest
  value.  Returns 'default' if the dict is empty."""
  x = [(v, k) for (k, v) in d.iteritems()]
  if not x: return default
  x.sort()
  return x[-1][1]


def IsSymlink(info):
  """Return true if the zipfile.ZipInfo object passed in represents a
  symlink."""
  return (info.external_attr >> 16) & 0770000 == 0120000

def IsRegular(info):
  """Return true if the zipfile.ZipInfo object passed in represents a
  symlink."""
  return (info.external_attr >> 28) == 010

def ClosestFileMatch(src, tgtfiles, existing):
  """Returns the closest file match between a source file and list
     of potential matches.  The exact filename match is preferred,
     then the sha1 is searched for, and finally a file with the same
     basename is evaluated.  Rename support in the updater-binary is
     required for the latter checks to be used."""

  result = tgtfiles.get("path:" + src.name)
  if result is not None:
    return result

  if not OPTIONS.target_info_dict.get("update_rename_support", False):
    return None

  if src.size < 1000:
    return None

  result = tgtfiles.get("sha1:" + src.sha1)
  if result is not None and existing.get(result.name) is None:
    return result
  result = tgtfiles.get("file:" + src.name.split("/")[-1])
  if result is not None and existing.get(result.name) is None:
    return result
  return None

class Item:
  """Items represent the metadata (user, group, mode) of files and
  directories in the system image."""
  ITEMS = {}
  def __init__(self, name, dir=False):
    self.name = name
    self.uid = None
    self.gid = None
    self.mode = None
    self.selabel = None
    self.capabilities = None
    self.dir = dir

    if name:
      self.parent = Item.Get(os.path.dirname(name), dir=True)
      self.parent.children.append(self)
    else:
      self.parent = None
    if dir:
      self.children = []

  def Dump(self, indent=0):
    if self.uid is not None:
      print "%s%s %d %d %o" % ("  "*indent, self.name, self.uid, self.gid, self.mode)
    else:
      print "%s%s %s %s %s" % ("  "*indent, self.name, self.uid, self.gid, self.mode)
    if self.dir:
      print "%s%s" % ("  "*indent, self.descendants)
      print "%s%s" % ("  "*indent, self.best_subtree)
      for i in self.children:
        i.Dump(indent=indent+1)

  @classmethod
  def Get(cls, name, dir=False):
    if name not in cls.ITEMS:
      cls.ITEMS[name] = Item(name, dir=dir)
    return cls.ITEMS[name]

  @classmethod
  def GetMetadata(cls, input_zip):

    # The target_files contains a record of what the uid,
    # gid, and mode are supposed to be.
    output = input_zip.read("META/filesystem_config.txt")

    for line in output.split("\n"):
      if not line: continue
      columns = line.split()
      name, uid, gid, mode = columns[:4]
      selabel = None
      capabilities = None

      # After the first 4 columns, there are a series of key=value
      # pairs. Extract out the fields we care about.
      for element in columns[4:]:
        key, value = element.split("=")
        if key == "selabel":
          selabel = value
        if key == "capabilities":
          capabilities = value

      i = cls.ITEMS.get(name, None)
      if i is not None:
        i.uid = int(uid)
        i.gid = int(gid)
        i.mode = int(mode, 8)
        i.selabel = selabel
        i.capabilities = capabilities
        if i.dir:
          i.children.sort(key=lambda i: i.name)

    # set metadata for the files generated by this script.
    i = cls.ITEMS.get("system/recovery-from-boot.p", None)
    if i: i.uid, i.gid, i.mode, i.selabel, i.capabilities = 0, 0, 0644, None, None
    i = cls.ITEMS.get("system/etc/install-recovery.sh", None)
    if i: i.uid, i.gid, i.mode, i.selabel, i.capabilities = 0, 0, 0544, None, None

  def CountChildMetadata(self):
    """Count up the (uid, gid, mode, selabel, capabilities) tuples for
    all children and determine the best strategy for using set_perm_recursive and
    set_perm to correctly chown/chmod all the files to their desired
    values.  Recursively calls itself for all descendants.

    Returns a dict of {(uid, gid, dmode, fmode, selabel, capabilities): count} counting up
    all descendants of this node.  (dmode or fmode may be None.)  Also
    sets the best_subtree of each directory Item to the (uid, gid,
    dmode, fmode, selabel, capabilities) tuple that will match the most
    descendants of that Item.
    """

    assert self.dir
    d = self.descendants = {(self.uid, self.gid, self.mode, None, self.selabel, self.capabilities): 1}
    for i in self.children:
      if i.dir:
        for k, v in i.CountChildMetadata().iteritems():
          d[k] = d.get(k, 0) + v
      else:
        k = (i.uid, i.gid, None, i.mode, i.selabel, i.capabilities)
        d[k] = d.get(k, 0) + 1

    # Find the (uid, gid, dmode, fmode, selabel, capabilities)
    # tuple that matches the most descendants.

    # First, find the (uid, gid) pair that matches the most
    # descendants.
    ug = {}
    for (uid, gid, _, _, _, _), count in d.iteritems():
      ug[(uid, gid)] = ug.get((uid, gid), 0) + count
    ug = MostPopularKey(ug, (0, 0))

    # Now find the dmode, fmode, selabel, and capabilities that match
    # the most descendants with that (uid, gid), and choose those.
    best_dmode = (0, 0755)
    best_fmode = (0, 0644)
    best_selabel = (0, None)
    best_capabilities = (0, None)
    for k, count in d.iteritems():
      if k[:2] != ug: continue
      if k[2] is not None and count >= best_dmode[0]: best_dmode = (count, k[2])
      if k[3] is not None and count >= best_fmode[0]: best_fmode = (count, k[3])
      if k[4] is not None and count >= best_selabel[0]: best_selabel = (count, k[4])
      if k[5] is not None and count >= best_capabilities[0]: best_capabilities = (count, k[5])
    self.best_subtree = ug + (best_dmode[1], best_fmode[1], best_selabel[1], best_capabilities[1])

    return d

  def SetPermissions(self, script):
    """Append set_perm/set_perm_recursive commands to 'script' to
    set all permissions, users, and groups for the tree of files
    rooted at 'self'."""

    self.CountChildMetadata()

    def recurse(item, current):
      # current is the (uid, gid, dmode, fmode, selabel, capabilities) tuple that the current
      # item (and all its children) have already been set to.  We only
      # need to issue set_perm/set_perm_recursive commands if we're
      # supposed to be something different.
      if item.dir:
        if current != item.best_subtree:
          script.SetPermissionsRecursive("/"+item.name, *item.best_subtree)
          current = item.best_subtree

        if item.uid != current[0] or item.gid != current[1] or \
           item.mode != current[2] or item.selabel != current[4] or \
           item.capabilities != current[5]:
          script.SetPermissions("/"+item.name, item.uid, item.gid,
                                item.mode, item.selabel, item.capabilities)

        for i in item.children:
          recurse(i, current)
      else:
        if item.uid != current[0] or item.gid != current[1] or \
               item.mode != current[3] or item.selabel != current[4] or \
               item.capabilities != current[5]:
          script.SetPermissions("/"+item.name, item.uid, item.gid,
                                item.mode, item.selabel, item.capabilities)

    recurse(self, (-1, -1, -1, -1, None, None))


def CopySystemFiles(input_zip, output_zip=None,
                    substitute=None):
  """Copies files underneath system/ in the input zip to the output
  zip.  Populates the Item class with their metadata, and returns a
  list of symlinks.  output_zip may be None, in which case the copy is
  skipped (but the other side effects still happen).  substitute is an
  optional dict of {output filename: contents} to be output instead of
  certain input files.
  """

  symlinks = []

  for info in input_zip.infolist():
    if info.filename.startswith("SYSTEM/"):
      basefilename = info.filename[7:]
      if IsSymlink(info):
        symlinks.append((input_zip.read(info.filename),
                         "/system/" + basefilename))
      else:
        info2 = copy.copy(info)
        fn = info2.filename = "system/" + basefilename
        if substitute and fn in substitute and substitute[fn] is None:
          continue
        if output_zip is not None:
          if substitute and fn in substitute:
            data = substitute[fn]
          else:
            data = input_zip.read(info.filename)
          output_zip.writestr(info2, data)
        if fn.endswith("/"):
          Item.Get(fn[:-1], dir=True)
        else:
          Item.Get(fn, dir=False)

  symlinks.sort()
  return symlinks


def SignOutput(temp_zip_name, output_zip_name):
  key_passwords = common.GetKeyPasswords([OPTIONS.package_key])
  pw = key_passwords[OPTIONS.package_key]

  common.SignFile(temp_zip_name, output_zip_name, OPTIONS.package_key, pw,
                  whole_file=True)


def AppendAssertions(script, info_dict):
  if OPTIONS.override_device == "auto":
    if OPTIONS.override_prop:
      device = GetBuildProp("ro.build.product", info_dict)
    else:
      device = GetBuildProp("ro.product.device", info_dict)
  else:
    device = OPTIONS.override_device
  script.AssertDevice(device)


def MakeRecoveryPatch(input_tmp, output_zip, recovery_img, boot_img):
  """Generate a binary patch that creates the recovery image starting
  with the boot image.  (Most of the space in these images is just the
  kernel, which is identical for the two, so the resulting patch
  should be efficient.)  Add it to the output zip, along with a shell
  script that is run from init.rc on first boot to actually do the
  patching and install the new recovery image.

  recovery_img and boot_img should be File objects for the
  corresponding images.  info should be the dictionary returned by
  common.LoadInfoDict() on the input target_files.

  Returns an Item for the shell script, which must be made
  executable.
  """

  diff_program = ["imgdiff"]
  path = os.path.join(input_tmp, "SYSTEM", "etc", "recovery-resource.dat")
  if os.path.exists(path):
    diff_program.append("-b")
    diff_program.append(path)
    bonus_args = "-b /system/etc/recovery-resource.dat"
  else:
    bonus_args = ""

  d = common.Difference(recovery_img, boot_img, diff_program=diff_program)
  _, _, patch = d.ComputePatch()
  common.ZipWriteStr(output_zip, "recovery/recovery-from-boot.p", patch)
  Item.Get("system/recovery-from-boot.p", dir=False)

  boot_type, boot_device = common.GetTypeAndDevice("/boot", OPTIONS.info_dict)
  recovery_type, recovery_device = common.GetTypeAndDevice("/recovery", OPTIONS.info_dict)

  sh = """#!/system/bin/sh
if ! applypatch -c %(recovery_type)s:%(recovery_device)s:%(recovery_size)d:%(recovery_sha1)s; then
  log -t recovery "Installing new recovery image"
  applypatch %(bonus_args)s %(boot_type)s:%(boot_device)s:%(boot_size)d:%(boot_sha1)s %(recovery_type)s:%(recovery_device)s %(recovery_sha1)s %(recovery_size)d %(boot_sha1)s:/system/recovery-from-boot.p
else
  log -t recovery "Recovery image already installed"
fi
""" % { 'boot_size': boot_img.size,
        'boot_sha1': boot_img.sha1,
        'recovery_size': recovery_img.size,
        'recovery_sha1': recovery_img.sha1,
        'boot_type': boot_type,
        'boot_device': boot_device,
        'recovery_type': recovery_type,
        'recovery_device': recovery_device,
        'bonus_args': bonus_args,
        }
  common.ZipWriteStr(output_zip, "recovery/etc/install-recovery.sh", sh)
  return Item.Get("system/etc/install-recovery.sh", dir=False)


def WriteFullOTAPackage(input_zip, output_zip):
  # TODO: how to determine this?  We don't know what version it will
  # be installed on top of.  For now, we expect the API just won't
  # change very often.
  script = edify_generator.EdifyGenerator(3, OPTIONS.info_dict)

  if OPTIONS.override_prop:
    metadata = {"post-timestamp": GetBuildProp("ro.build.date.utc",
                                               OPTIONS.info_dict),
                }
  else:
    metadata = {"post-build": GetBuildProp("ro.build.fingerprint",
                                           OPTIONS.info_dict),
                "pre-device": GetBuildProp("ro.product.device",
                                           OPTIONS.info_dict),
                "post-timestamp": GetBuildProp("ro.build.date.utc",
                                               OPTIONS.info_dict),
                }

  device_specific = common.DeviceSpecificParams(
      input_zip=input_zip,
      input_version=OPTIONS.info_dict["recovery_api_version"],
      output_zip=output_zip,
      script=script,
      input_tmp=OPTIONS.input_tmp,
      metadata=metadata,
      info_dict=OPTIONS.info_dict)

  #if not OPTIONS.omit_prereq:
  #  ts = GetBuildProp("ro.build.date.utc", OPTIONS.info_dict)
  #  ts_text = GetBuildProp("ro.build.date", OPTIONS.info_dict)
  #  script.AssertOlderBuild(ts, ts_text)

  AppendAssertions(script, OPTIONS.info_dict)
  device_specific.FullOTA_Assertions()
  device_specific.FullOTA_InstallBegin()

  if OPTIONS.backuptool:
    script.Mount("/system")
    script.RunBackup("backup")
    script.Unmount("/system")

  script.ShowProgress(0.5, 0)

  if OPTIONS.wipe_user_data:
    script.FormatPartition("/data")

  if "selinux_fc" in OPTIONS.info_dict:
    WritePolicyConfig(OPTIONS.info_dict["selinux_fc"], output_zip)

  script.FormatPartition("/system")
  script.Mount("/system")
  #script.UnpackPackageDir("recovery", "/system")
  script.UnpackPackageDir("system", "/system")

  symlinks = CopySystemFiles(input_zip, output_zip)
  script.MakeSymlinks(symlinks)

  boot_img = common.GetBootableImage("boot.img", "boot.img",
                                     OPTIONS.input_tmp, "BOOT")
  #recovery_img = common.GetBootableImage("recovery.img", "recovery.img",
  #                                       OPTIONS.input_tmp, "RECOVERY")
  #MakeRecoveryPatch(OPTIONS.input_tmp, output_zip, recovery_img, boot_img)

  Item.GetMetadata(input_zip)
  Item.Get("system").SetPermissions(script)

  common.CheckSize(boot_img.data, "boot.img", OPTIONS.info_dict)
  common.ZipWriteStr(output_zip, "boot.img", boot_img.data)
  script.ShowProgress(0.2, 0)

  if OPTIONS.backuptool:
    script.ShowProgress(0.2, 10)
    script.RunBackup("restore")

  script.ShowProgress(0.2, 10)
  script.WriteRawImage("/boot", "boot.img")

  script.ShowProgress(0.1, 0)
  device_specific.FullOTA_InstallEnd()

  if OPTIONS.extra_script is not None:
    script.AppendExtra(OPTIONS.extra_script)

  script.UnmountAll()
  script.AddToZip(input_zip, output_zip)
  WriteMetadata(metadata, output_zip)

def WritePolicyConfig(file_context, output_zip):
  f = open(file_context, 'r');
  basename = os.path.basename(file_context)
  common.ZipWriteStr(output_zip, basename, f.read())


def WriteMetadata(metadata, output_zip):
  common.ZipWriteStr(output_zip, "META-INF/com/android/metadata",
                     "".join(["%s=%s\n" % kv
                              for kv in sorted(metadata.iteritems())]))

def LoadSystemFiles(z):
  """Load all the files from SYSTEM/... in a given target-files
  ZipFile, and return a dict of {filename: File object}."""
  out = {}
  for info in z.infolist():
    if info.filename.startswith("SYSTEM/") and not IsSymlink(info):
      basefilename = info.filename[7:]
      fn = "system/" + basefilename
      data = z.read(info.filename)
      out[fn] = common.File(fn, data)
  return out


def GetBuildProp(prop, info_dict):
  """Return the fingerprint of the build of a given target-files info_dict."""
  try:
    return info_dict.get("build.prop", {})[prop]
  except KeyError:
    raise common.ExternalError("couldn't find %s in build.prop" % (property,))


def WriteIncrementalOTAPackage(target_zip, source_zip, output_zip):
  source_version = OPTIONS.source_info_dict["recovery_api_version"]
  target_version = OPTIONS.target_info_dict["recovery_api_version"]

  if source_version == 0:
    print ("WARNING: generating edify script for a source that "
           "can't install it.")
  script = edify_generator.EdifyGenerator(source_version,
                                          OPTIONS.target_info_dict)

  if OPTIONS.override_prop:
    metadata = {"post-timestamp": GetBuildProp("ro.build.date.utc",
                                               OPTIONS.target_info_dict),
                }
  else:
    metadata = {"pre-device": GetBuildProp("ro.product.device",
                                           OPTIONS.source_info_dict),
                "post-timestamp": GetBuildProp("ro.build.date.utc",
                                               OPTIONS.target_info_dict),
                }

  device_specific = common.DeviceSpecificParams(
      source_zip=source_zip,
      source_version=source_version,
      target_zip=target_zip,
      target_version=target_version,
      output_zip=output_zip,
      script=script,
      metadata=metadata,
      info_dict=OPTIONS.info_dict)

  print "Loading target..."
  target_data = LoadSystemFiles(target_zip)
  print "Loading source..."
  source_data = LoadSystemFiles(source_zip)

  verbatim_targets = []
  patch_list = []
  diffs = []
  renames = {}
  largest_source_size = 0

  matching_file_cache = {}
  for fn in source_data.keys():
    sf = source_data[fn]
    assert fn == sf.name
    matching_file_cache["path:" + fn] = sf
    # Only allow eligability for filename/sha matching
    # if there isn't a perfect path match.
    if target_data.get(sf.name) is None:
      matching_file_cache["file:" + fn.split("/")[-1]] = sf
      matching_file_cache["sha:" + sf.sha1] = sf

  for fn in sorted(target_data.keys()):
    tf = target_data[fn]
    assert fn == tf.name
    sf = ClosestFileMatch(tf, matching_file_cache, renames)
    if sf is not None and sf.name != tf.name:
      print "File has moved from " + sf.name + " to " + tf.name
      renames[sf.name] = tf

    if sf is None or fn in OPTIONS.require_verbatim:
      # This file should be included verbatim
      if fn in OPTIONS.prohibit_verbatim:
        raise common.ExternalError("\"%s\" must be sent verbatim" % (fn,))
      print "send", fn, "verbatim"
      tf.AddToZip(output_zip)
      verbatim_targets.append((fn, tf.size))
    elif tf.sha1 != sf.sha1:
      # File is different; consider sending as a patch
      diffs.append(common.Difference(tf, sf))
    else:
      # Target file data identical to source (may still be renamed)
      pass

#  common.ComputeDifferences(diffs)
#
#  for diff in diffs:
#    tf, sf, d = diff.GetPatch()
#    if d is None or len(d) > tf.size * OPTIONS.patch_threshold:
#      # patch is almost as big as the file; don't bother patching
#      tf.AddToZip(output_zip)
#      verbatim_targets.append((tf.name, tf.size))
#    else:
#      common.ZipWriteStr(output_zip, "patch/" + sf.name + ".p", d)
#      patch_list.append((sf.name, tf, sf, tf.size, common.sha1(d).hexdigest()))
#      largest_source_size = max(largest_source_size, sf.size)

  if not OPTIONS.override_prop:
    source_fp = GetBuildProp("ro.build.fingerprint", OPTIONS.source_info_dict)
    target_fp = GetBuildProp("ro.build.fingerprint", OPTIONS.target_info_dict)
    metadata["pre-build"] = source_fp
    metadata["post-build"] = target_fp

    script.Mount("/system")
    script.AssertSomeFingerprint(source_fp, target_fp)

  source_boot = common.GetBootableImage(
      "/tmp/boot.img", "boot.img", OPTIONS.source_tmp, "BOOT",
      OPTIONS.source_info_dict)
  target_boot = common.GetBootableImage(
      "/tmp/boot.img", "boot.img", OPTIONS.target_tmp, "BOOT")
  updating_boot = (source_boot.data != target_boot.data)

  #source_recovery = common.GetBootableImage(
  #    "/tmp/recovery.img", "recovery.img", OPTIONS.source_tmp, "RECOVERY",
  #    OPTIONS.source_info_dict)
  #target_recovery = common.GetBootableImage(
  #    "/tmp/recovery.img", "recovery.img", OPTIONS.target_tmp, "RECOVERY")
  #updating_recovery = (source_recovery.data != target_recovery.data)
  updating_recovery = False

  # Here's how we divide up the progress bar:
  #  0.1 for verifying the start state (PatchCheck calls)
  #  0.8 for applying patches (ApplyPatch calls)
  #  0.1 for unpacking verbatim files, symlinking, and doing the
  #      device-specific commands.

  AppendAssertions(script, OPTIONS.target_info_dict)
  device_specific.IncrementalOTA_Assertions()

  script.Print("Verifying current system...")

  device_specific.IncrementalOTA_VerifyBegin()

  script.ShowProgress(0.1, 0)
  total_verify_size = float(sum([i[2].size for i in patch_list]) + 1)
  if updating_boot:
    total_verify_size += source_boot.size
  so_far = 0

  for fn, tf, sf, size, patch_sha in patch_list:
    script.PatchCheck("/"+fn, tf.sha1, sf.sha1)
    so_far += sf.size
    script.SetProgress(so_far / total_verify_size)

  if updating_boot:
    d = common.Difference(target_boot, source_boot)
    _, _, d = d.ComputePatch()
    print "boot      target: %d  source: %d  diff: %d" % (
        target_boot.size, source_boot.size, len(d))

    common.ZipWriteStr(output_zip, "patch/boot.img.p", d)

    boot_type, boot_device = common.GetTypeAndDevice("/boot", OPTIONS.info_dict)

    script.PatchCheck("%s:%s:%d:%s:%d:%s" %
                      (boot_type, boot_device,
                       source_boot.size, source_boot.sha1,
                       target_boot.size, target_boot.sha1))
    so_far += source_boot.size
    script.SetProgress(so_far / total_verify_size)

  if patch_list or updating_recovery or updating_boot:
    script.CacheFreeSpaceCheck(largest_source_size)

  device_specific.IncrementalOTA_VerifyEnd()

  script.Comment("---- start making changes here ----")

  device_specific.IncrementalOTA_InstallBegin()

  if OPTIONS.wipe_user_data:
    script.Print("Erasing user data...")
    script.FormatPartition("/data")

  script.Print("Removing unneeded files...")
  script.DeleteFiles(["/"+i[0] for i in verbatim_targets] +
                     ["/"+i for i in sorted(source_data)
                            if i not in target_data and
                            i not in renames] +
                     ["/system/recovery.img"])

  script.ShowProgress(0.8, 0)
  total_patch_size = float(sum([i[1].size for i in patch_list]) + 1)
  if updating_boot:
    total_patch_size += target_boot.size
  so_far = 0

  script.Print("Patching system files...")
  deferred_patch_list = []
  for item in patch_list:
    fn, tf, sf, size, _ = item
    if tf.name == "system/build.prop":
      deferred_patch_list.append(item)
      continue
    script.ApplyPatch("/"+fn, "-", tf.size, tf.sha1, sf.sha1, "patch/"+fn+".p")
    so_far += tf.size
    script.SetProgress(so_far / total_patch_size)

  if updating_boot:
    # Produce the boot image by applying a patch to the current
    # contents of the boot partition, and write it back to the
    # partition.
    script.Print("Patching boot image...")
    script.ApplyPatch("%s:%s:%d:%s:%d:%s"
                      % (boot_type, boot_device,
                         source_boot.size, source_boot.sha1,
                         target_boot.size, target_boot.sha1),
                      "-",
                      target_boot.size, target_boot.sha1,
                      source_boot.sha1, "patch/boot.img.p")
    so_far += target_boot.size
    script.SetProgress(so_far / total_patch_size)
    print "boot image changed; including."
  else:
    print "boot image unchanged; skipping."

  if updating_recovery:
    # Recovery is generated as a patch using both the boot image
    # (which contains the same linux kernel as recovery) and the file
    # /system/etc/recovery-resource.dat (which contains all the images
    # used in the recovery UI) as sources.  This lets us minimize the
    # size of the patch, which must be included in every OTA package.
    #
    # For older builds where recovery-resource.dat is not present, we
    # use only the boot image as the source.

    MakeRecoveryPatch(OPTIONS.target_tmp, output_zip,
                      target_recovery, target_boot)
    script.DeleteFiles(["/system/recovery-from-boot.p",
                        "/system/etc/install-recovery.sh"])
    print "recovery image changed; including as patch from boot."
  else:
    print "recovery image unchanged; skipping."

  script.ShowProgress(0.1, 10)

  target_symlinks = CopySystemFiles(target_zip, None)

  target_symlinks_d = dict([(i[1], i[0]) for i in target_symlinks])
  temp_script = script.MakeTemporary()
  Item.GetMetadata(target_zip)
  Item.Get("system").SetPermissions(temp_script)

  # Note that this call will mess up the tree of Items, so make sure
  # we're done with it.
  source_symlinks = CopySystemFiles(source_zip, None)
  source_symlinks_d = dict([(i[1], i[0]) for i in source_symlinks])

  # Delete all the symlinks in source that aren't in target.  This
  # needs to happen before verbatim files are unpacked, in case a
  # symlink in the source is replaced by a real file in the target.
  to_delete = []
  for dest, link in source_symlinks:
    if link not in target_symlinks_d:
      to_delete.append(link)
  script.DeleteFiles(to_delete)

  if verbatim_targets:
    script.Print("Unpacking new files...")
    script.UnpackPackageDir("system", "/system")

  #if updating_recovery:
  #  script.Print("Unpacking new recovery...")
  #  script.UnpackPackageDir("recovery", "/system")

  if len(renames) > 0:
    script.Print("Renaming files...")

  for src in renames:
    print "Renaming " + src + " to " + renames[src].name
    script.RenameFile(src, renames[src].name)

  script.Print("Symlinks and permissions...")

  # Create all the symlinks that don't already exist, or point to
  # somewhere different than what we want.  Delete each symlink before
  # creating it, since the 'symlink' command won't overwrite.
  to_create = []
  for dest, link in target_symlinks:
    if link in source_symlinks_d:
      if dest != source_symlinks_d[link]:
        to_create.append((dest, link))
    else:
      to_create.append((dest, link))
  script.DeleteFiles([i[1] for i in to_create])
  script.MakeSymlinks(to_create)

  # Now that the symlinks are created, we can set all the
  # permissions.
  script.AppendScript(temp_script)

  # Do device-specific installation (eg, write radio image).
  device_specific.IncrementalOTA_InstallEnd()

  if OPTIONS.extra_script is not None:
    script.AppendExtra(OPTIONS.extra_script)

  # Patch the build.prop file last, so if something fails but the
  # device can still come up, it appears to be the old build and will
  # get set the OTA package again to retry.
  script.Print("Patching remaining system files...")
  for item in deferred_patch_list:
    fn, tf, sf, size, _ = item
    script.ApplyPatch("/"+fn, "-", tf.size, tf.sha1, sf.sha1, "patch/"+fn+".p")
  script.SetPermissions("/system/build.prop", 0, 0, 0644, None, None)

  script.AddToZip(target_zip, output_zip)
  WriteMetadata(metadata, output_zip)


def main(argv):

  def option_handler(o, a):
    if o in ("-b", "--board_config"):
      pass   # deprecated
    elif o in ("-k", "--package_key"):
      OPTIONS.package_key = a
    elif o in ("-i", "--incremental_from"):
      OPTIONS.incremental_source = a
    elif o in ("-w", "--wipe_user_data"):
      OPTIONS.wipe_user_data = True
    elif o in ("-n", "--no_prereq"):
      OPTIONS.omit_prereq = True
    elif o in ("-e", "--extra_script"):
      OPTIONS.extra_script = a
    elif o in ("-a", "--aslr_mode"):
      if a in ("on", "On", "true", "True", "yes", "Yes"):
        OPTIONS.aslr_mode = True
      else:
        OPTIONS.aslr_mode = False
    elif o in ("--worker_threads"):
      OPTIONS.worker_threads = int(a)
    elif o in ("--backup"):
      OPTIONS.backuptool = bool(a.lower() == 'true')
    elif o in ("--override_device"):
      OPTIONS.override_device = a
    elif o in ("--override_prop"):
      OPTIONS.override_prop = bool(a.lower() == 'true')
    else:
      return False
    return True

  args = common.ParseOptions(argv, __doc__,
                             extra_opts="b:k:i:d:wne:a:",
                             extra_long_opts=["board_config=",
                                              "package_key=",
                                              "incremental_from=",
                                              "wipe_user_data",
                                              "no_prereq",
                                              "extra_script=",
                                              "worker_threads=",
                                              "aslr_mode=",
                                              "backup=",
                                              "override_device=",
                                              "override_prop="],
                             extra_option_handler=option_handler)

  if len(args) < 2:
    common.Usage(__doc__)
    sys.exit(1)

  for arg in args[2:]:
    OPTIONS.require_verbatim.add(arg)
  print "OPTIONS.require_verbatim: %r" % OPTIONS.require_verbatim

  if OPTIONS.extra_script is not None:
    OPTIONS.extra_script = open(OPTIONS.extra_script).read()

  print "unzipping target target-files..."
  OPTIONS.input_tmp, input_zip = common.UnzipTemp(args[0])

  OPTIONS.target_tmp = OPTIONS.input_tmp
  OPTIONS.info_dict = common.LoadInfoDict(input_zip)

  # If this image was originally labelled with SELinux contexts, make sure we
  # also apply the labels in our new image. During building, the "file_contexts"
  # is in the out/ directory tree, but for repacking from target-files.zip it's
  # in the root directory of the ramdisk.
  if "selinux_fc" in OPTIONS.info_dict:
    OPTIONS.info_dict["selinux_fc"] = os.path.join(OPTIONS.input_tmp, "BOOT", "RAMDISK",
        "file_contexts")

  if OPTIONS.verbose:
    print "--- target info ---"
    common.DumpInfoDict(OPTIONS.info_dict)

  if OPTIONS.device_specific is None:
    OPTIONS.device_specific = OPTIONS.info_dict.get("tool_extensions", None)
  if OPTIONS.device_specific is not None:
    OPTIONS.device_specific = os.path.normpath(OPTIONS.device_specific)
    print "using device-specific extensions in", OPTIONS.device_specific

  temp_zip_file = tempfile.NamedTemporaryFile()
  output_zip = zipfile.ZipFile(temp_zip_file, "w",
                               compression=zipfile.ZIP_DEFLATED)

  if OPTIONS.incremental_source is None:
    WriteFullOTAPackage(input_zip, output_zip)
    if OPTIONS.package_key is None:
      OPTIONS.package_key = OPTIONS.info_dict.get(
          "default_system_dev_certificate",
          "build/target/product/security/testkey")
  else:
    print "unzipping source target-files..."
    OPTIONS.source_tmp, source_zip = common.UnzipTemp(OPTIONS.incremental_source)
    OPTIONS.target_info_dict = OPTIONS.info_dict
    OPTIONS.source_info_dict = common.LoadInfoDict(source_zip)
    if OPTIONS.package_key is None:
      OPTIONS.package_key = OPTIONS.source_info_dict.get(
          "default_system_dev_certificate",
          "build/target/product/security/testkey")
    if OPTIONS.verbose:
      print "--- source info ---"
      common.DumpInfoDict(OPTIONS.source_info_dict)
    WriteIncrementalOTAPackage(input_zip, source_zip, output_zip)

  output_zip.close()

  SignOutput(temp_zip_file.name, args[1])
  temp_zip_file.close()

  common.Cleanup()

  print "done."


if __name__ == '__main__':
  try:
    common.CloseInheritedPipes()
    main(sys.argv[1:])
  except common.ExternalError, e:
    print
    print "   ERROR: %s" % (e,)
    print
    sys.exit(1)
