#! /bin/bash
#
# Paranoid Android 4.x gapps clears out /tmp after completing the installation.
# This causes issues when the recovery image is still appending data to files in /tmp.
#
# This script removes the rm -rf from any pa_gapps* distribution.
#

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 [gapps.zip]"
    exit 1
fi

ORIG_ZIP=$1
# If this isn't a fully qualified path, prefix the current working directory
if [[ ! "${ORIG_ZIP}" =~ ^\/.* ]]; then
    ORIG_ZIP=`pwd`/${ORIG_ZIP}
fi

if [[ ! -f "${ORIG_ZIP}" ]]; then
    echo "Cannot locate file ${ORIG_ZIP}"
    exit 2
fi

NEW_ZIP=$(echo "${ORIG_ZIP}" | sed -e 's/\.zip$/-keeptmp.zip/')
if [[ -f "${NEW_ZIP}" ]]; then
    echo "Destination file already exists: ${NEW_ZIP}"
    exit 3
fi
echo "Writing to ${NEW_ZIP}"

if [[ $(uname -s) == "Darwin" ]]; then
    TMPDIR=$(mktemp -d -t /tmp)
else
    TMPDIR=$(mktemp -d)
fi
echo $TMPDIR

cd $TMPDIR &&
unzip ${ORIG_ZIP} META-INF/com/google/android/update-binary &&
patch -p0 <<EOF
--- META-INF/com/google/android/update-binary   2008-02-28 21:33:46.000000000 -0800
+++ META-INF/com/google/android/update-binary.old       2015-02-10 10:14:32.813865164 -0800
@@ -92,7 +92,6 @@
         tar -cz -f "$log_folder/pa_gapps_debug_logs.tar.gz" *;
         cd /;
     fi;
-    rm -rf /tmp/*;
     set_progress 1.0;
     ui_print "- Unmounting /system, /data, /cache";
     ui_print " ";
EOF

cp -v "${ORIG_ZIP}" "${NEW_ZIP}" &&
pushd "${TMP_DIR}" &&
zip -r9 "${NEW_ZIP}" META-INF/com/google/android/update-binary
popd &&
rm -fv "${NEW_ZIP}.md5sum" &&
if [[ $(uname -s) == "Darwin" ]]; then
    md5 -q ${NEW_ZIP} > "${NEW_ZIP}.md5sum"
else
    md5sum ${NEW_ZIP} > "${NEW_ZIP}.md5sum"
fi
