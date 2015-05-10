#!/bin/bash

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

echo "Usage: ${progName} --device=<device_name>"
echo "  [--dist=<android-5.1.1_r1|cm-12.0>]: Android distribution."
echo "  [--numrows=<n>]: Items to return."
echo "  [--pipeline_number=<n>]: Filter by pipeline number."
echo "  [--build_number=<n>]: Filter by build number."

echo ""
echo "Not yet implemented"
exit 1
