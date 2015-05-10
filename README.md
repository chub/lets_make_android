#Let's Make Android

Let's Make Android (LMA) manages Android builds and keeps your device
up-to-date.

##Build

Designed for continuous integration using the [Gerrit Jenkins Plugin](https://wiki.jenkins-ci.org/display/JENKINS/Gerrit+Trigger).  The build script executes for each commit, but also tries to detect stacked changes - multiple changes to the same repository - and skips the intermediate changes.

##Flash

The flash performs several tasks, usually in one run:
* installs or updates a compatible recovery;
* installs or updates the ROM;
* installs or updates GApps;
* installs or updates individual APKs; and
* installs listed sideload zip.

On supported ROMs, the flash script also:
* detects when the signing key of the platform has changed (necessitating a data wipe); and
* detects when a sideloading zip requires a newer or older ROM.

Devices must be unlocked, and have a sensible bootloader.

## LMA Supported Devices

The code copes with observed exceptions and differences of the following devices:
* Google Nexus 4
* Google Nexus 5
* Google Nexus 7 (2012)
* Google Nexus 7 (2013)
* Google Nexus 9
* OnePlus One

The following devices have successfully worked with this code in the past, but are not considered supported in the present:
* Moto E
* Sony Z3 Phone
* Sony Z3 Tablet
* Google Nexus S
* Google Galaxy Nexus
* Google Nexus 10

## LMA Supported Hosts

These scripts should work with Linux and Mac OS X.

##Contributions

This project was open-sourced from a closed repo, so rough edges are expected, especially around file retrieval and other integration points.

These tools are more than a year mature, and include fixes after more than a year of use and bugfixing.  Sadly the git history is not available for these fixes.
