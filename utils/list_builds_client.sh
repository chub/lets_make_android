#!/bin/bash
#
# Finds and lists client artifacts.

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

echo "Usage: ${progName} \\"
echo "  [--artifact=<aosp|CmRom|SideloadableOtaBuild|SingleApkBuild]: Artifact to search for."
echo "  [--dist=<android-5.1.1_r1|cm-12.0>]: Android distribution."
echo "  [--build_number=<n>]: Filter by Jenkins build number."
echo "  [--pipeline_number=<n>]: Filter by pipeline number."
echo "  [--device=hammerhead|bacon|etc]: Device to select. Optional, but required if artifact=aosp."
echo "  [--numrows=<n>]: Items to return."

echo ""
echo "Not yet implemented"
exit 1
