#!/bin/sh
# READ README.md FIRST. Do not paste blindly. Slot values below are for YOUR phone (current-slot: a).
#
# STEP 0 - the bootloader is LOCKED on your phone (fastboot: unlocked=no, ro.boot.flash.locked=1).
#          Nothing custom can be flashed until it is unlocked. Unlocking FACTORY-RESETS the phone
#          (you have no userdata backup: copy photos/chats off the phone first).
#   Settings > About phone > tap Build number 7x > Developer options > enable "OEM unlocking" + "USB debugging"
#   adb reboot bootloader
#   fastboot flashing unlock          # confirm on the phone with the volume keys
#   (if the OEM-unlock toggle is greyed out, or unlock is refused: stop and tell me, do not improvise)
#
# STEP 1 - make a safety copy that does not depend on fastboot (BROM / mtkclient), once:
#   python mtk r vendor_boot_a vendor_boot_a_backup.img
#   python mtk r vbmeta_a      vbmeta_a_backup.img
#   (compare sha256 with the files you already have)
#
# STEP 2 - flash (bootloader fastboot, is-userspace must say "no"):
fastboot getvar current-slot          # expect: a
fastboot getvar is-userspace          # expect: no
# Flash ONLY vendor_boot first. With an UNLOCKED bootloader a failed AVB check is normally just a warning (orange).
# If, and only if, the phone then sticks at the logo: also flash the fallback (your vbmeta_a with 1 byte changed):
#   fastboot flash vbmeta_a fallback/vbmeta_a_verification_disabled.img
# (restore later with your stock_vbmeta_a.img)
fastboot flash vendor_boot_a vendor_boot_twrp.img
# STEP 3 - boot recovery:  fastboot reboot recovery   (or power off, hold Vol Up + Power)
#
# ROLLBACK (any one of these):
#   fastboot flash vendor_boot_a vendor_boot.img                  # your stock image
#   python mtk w vendor_boot_a vendor_boot.img                    # BROM, works even with a dead fastboot
