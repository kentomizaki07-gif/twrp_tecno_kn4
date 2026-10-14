# TWRP for TECNO KN4 / Spark 50 (MT6769S / Helio G81, Android 16) — engineering package

TWRP base: **TWRP-Test/platform_manifest_twrp_aosp, branch `twrp-16.0`** (AOSP `android-16.0.0_r1`, TWRP-Test forks of recovery/build/bionic/system/*).

## 0. Status: what is verified and what is not

| Item | Status |
|---|---|
| vendor_boot repack reproduces your stock image **byte-for-byte**; only the recovery fragment is replaced (platform fragment with all kernel modules, DTB, cmdline untouched) | ✅ tested |
| **Images match the installed firmware**: the AVB data inside your `init_boot` / `vendor_boot` carries `16.3.0.140SP22_STB260808174446` / `MT6769-16.3.0.140SP22_STB260808174444`, identical to `ro.tran.system.version` / `ro.tran.vendor.version` on the phone; kernel string identical; build date Aug 2026 identical | ✅ checked against the phone |
| **vbmeta analysed**: `vbmeta_a` verifies `vendor_boot`, `init_boot`, `dtbo` directly (SHA-256 hash descriptors) and chains `boot`, `vbmeta_system`, `vbmeta_vendor`; all four of your images hash exactly to those descriptors (so they are the exact slot-a set the vbmeta vouches for); `boot_a` verifies against its chained key | ✅ checked on your files |
| Storage is **eMMC** (`mmcblk0`, `mmcblk0boot0/1` exist), by-name map, every partition name used in `recovery.fstab` exists on the phone | ✅ checked |
| Live `/data` flags = `fileencryption=aes-256-xts:aes-256-cts:v2,keydirectory=/metadata/vold/metadata_encryption`; `ro.crypto.type=file`, metadata encryption on; all system partitions are erofs | ✅ checked |
| Backlight `/sys/class/leds/lcd-backlight`, max **5119** | ✅ checked |
| Every module the phone has loaded that matters for display / touch / eMMC / USB / charging is in stock recovery's module list (the 37 not in it are modem, GPS, power-HAL, PTP etc.) | ✅ checked |
| Kernel has F2FS, EROFS, FS-encryption + inline crypt, dm-default-key, configfs USB (built in) | ✅ checked (`/proc/config.gz`) |
| Boot control is AIDL `IBootControl/default` served by `android.hardware.boot-service.mtk` (stock recovery uses the `_recovery` build, carried into the tree) | ✅ checked |
| `twrp-16.0` manifest + forks reachable, `mka vendorbootimage`, `lunch twrp_KN4-bp2a-eng`, every `TW_*` flag exists, obsolete A16 variables removed | ✅ checked |
| TWRP binary actually compiles with this tree / boots on the phone | ❌ not tested |
| /data decryption | ❌ needs the Trustonic vendor files (see §2.3) |

## 1. Device facts
* TECNO Spark 50 (model `TECNO KN4`, codename on the phone `TECNO-KN4`, product `KN4-OPPJ`), MT6769S, 4 GB, **eMMC**, HiOS 16.3.0.
* Vendor side is an **Android 15** stack (`vendor_dlkm` release 15, `AP3A`) under an **Android 16** MSSI system: that is why the ramdisks say Android 15 while the phone says 16. Not a mismatch.
* Recovery has no partition of its own: it is vendor-ramdisk fragment #2 (`type 2, name "recovery"`) in `vendor_boot` (header v4, 64 MiB). `boot` = kernel only, `init_boot` = generic ramdisk.
* Slots: A/B, **current slot a**, Virtual A/B (compressed), dynamic partitions (`super` = 10 764 070 912 bytes). `is-userspace: no` in bootloader fastboot.
* Kernel `6.6.118-android15-8-g0b9c3bf6db7f-ab14877662-4k` (GKI, modules signed).
* Verified boot is **green, enforcing, vbmeta digest locked** right now.
* Panel 720x1576, `ro.recovery.ui.margin_height=67`, BGRA_8888. Touch `chipone-tddi`, USB `musb-hdrc` + `mt_usb`, charger `sc8950`, TCPC `rt1711h`.
* Vendor partitions of note: `tee_a/b`, `lk_a/b`, `preloader_a/b` (= mmcblk0boot0/1), `nvram`, `nvdata`, `nvcfg`, `persist`, `protect1/2`, `seccfg`, `boot_para`, `tranfs`, `transec`, `tdfs`, plus `tr_*` logical partitions.

## 2. Blockers and risks (in the order they will bite)
1. **The bootloader is LOCKED** (`fastboot getvar unlocked` = no, `secure: yes`, `ro.boot.flash.locked=1`). A locked MediaTek bootloader will not boot a modified `vendor_boot`. It must be unlocked first, and **unlocking factory-resets the phone**; you have no userdata backup, so copy your personal data off first. If the OEM-unlocking toggle is greyed out or the unlock is refused, stop and tell me; mtkclient can change `seccfg` over BROM, but that is a different procedure and I want to look at your exact `seccfg`/`lk` state before you try it.
2. **AVB.** `vendor_boot` is verified by the main `vbmeta_a` hash descriptor, so the TWRP-carrying image will no longer match it. On a LOCKED bootloader that is fatal; after unlocking it is normally only a warning (orange state), so the first attempt flashes **only** `vendor_boot`. If the phone then stops at the logo, use `fallback/vbmeta_a_verification_disabled.img`: it is your own `vbmeta_a` with exactly one byte changed (flags 0 -> 3, i.e. what `fastboot --disable-verity --disable-verification` does). Stock hash: `1402c55d...f2ff`; fallback hash: `78040c1b...083d`. Keep your stock `vbmeta_a.img` to restore.
3. **/data decryption** needs the Trustonic stack from `/vendor` (keymint `IKeyMintDevice` v3.0, gatekeeper, secureclock, sharedsecret, `tee-service`, `mcDriverDaemon`, trustlets in `/vendor/app/mcRegistry`). A normal ADB shell can list those files but **cannot read them** (permission denied), so they were not collected. They are inside your `super` backup. This is phase 2, after the first boot works. Until then expect an encrypted /data; adb, sideload, fastbootd and raw-partition work do not need it.
4. `twrp-16.0` is a community test branch (TWRP-Test), not an official TeamWin release: expect to iterate on build errors.
5. SD/OTG nodes are set for eMMC (`mmcblk1p1`, `sda1`).

## 3. Package contents
```
tools/repack_vendor_boot.py      verified repack (self-test + post-verify, aborts on any mismatch)
tools/flash_guide.sh             fastboot sequence + rollback (read, don't blind-run)
fallback/vbmeta_a_verification_disabled.img   only if the phone stops at the logo (see §2.2)
device_tree/device/tecno/KN4/    BoardConfig.mk, twrp_KN4.mk, AndroidProducts.mk, system.prop,
                                 recovery/root/... (recovery.fstab from stock fstab.mt6768 + MTK blobs from stock)
.github/workflows/build-twrp.yml builds twrp-16.0 (TWRP-Test) on GitHub and outputs only the recovery ramdisk (no stock files are uploaded)
analysis/                        stock fstab, stock recovery init rc, stock recovery module load list
```

## 4. Procedure (order matters: unlock only when you already hold `vendor_boot_twrp.img`)
1. Back up your personal data and Google-account access (unlocking resets the phone). Keep your original `stock_vendor_boot_a.img` and `stock_vbmeta_a.img` safe.
2. Push this folder to a GitHub repo (no stock images needed there) and run **Build TWRP for TECNO KN4** (about 1-2 h; it syncs `TWRP-Test/platform_manifest_twrp_aosp -b twrp-16.0`, runs `lunch twrp_KN4-bp2a-eng` + `mka vendorbootimage`). Download the artifact `twrp_recovery_ramdisk_KN4` (one file, `ramdisk_recovery`). If the build fails, send me the failing log lines.
3. On your PC (Python 3 + `pip install lz4`), in the folder `tools`:
   `python repack_vendor_boot.py --stock <path>\stock_vendor_boot_a.img --ramdisk <path>\ramdisk_recovery --out vendor_boot_twrp.img`
   It must print `self-test OK` and `verify OK`; if not, do not flash.
4. Unlock the bootloader (`tools/flash_guide.sh`, step 0). If anything is refused, stop and tell me.
5. Make the BROM safety copy, then flash to slot **a** only (`tools/flash_guide.sh`, steps 1-3).
6. Rollback: `fastboot flash vendor_boot_a stock_vendor_boot_a.img`, or `python mtk w vendor_boot_a stock_vendor_boot_a.img` over BROM.

## 5. Still needed from you
* Whether the OEM-unlocking toggle is available.
* Phase 2 (decryption files, can be done in parallel): run `tools/extract_vendor_blobs.py` on your `stock_super.img` (instructions at the top of the file, uses WSL + `erofs-utils`), and send the small `kn4_vendor_blobs.zip`. Tested on a synthetic super/EROFS image; not yet on your real one.
