#!/bin/bash
#
# Finds or identifies pipeline metadata.

if [[ "${0}" = /* ]]; then ME="${0}"; else ME="${PWD}/${0}"; fi
while [ -h ${ME} ]; do ME=$(readlink $ME); done
source `dirname ${ME}`/../shell_base.sh

echo "Usage: ${progName}"
echo ""
echo " Identify mode:"
echo "  --pipeline_number=<n>: Identify a pipeline number."
echo "  [--showdist]: Display the distribution for the pipeline."
echo ""
echo " Search/List mode:"
echo "  --dist=<android-5.1.1_r1|cm-12.0>: Build distribution to list."
echo "  [--pipeline_number=<n>]: Search for a pipeline number."
echo "  [--numrows=<n>]: Items to return."

echo ""
echo "Not yet implemented"
exit 1
