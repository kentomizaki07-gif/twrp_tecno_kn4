#!/usr/bin/env python3
"""
Repack TECNO KN4 (MT6768/MT6769S) vendor_boot.img with a TWRP recovery ramdisk.

Only the *recovery* vendor-ramdisk fragment (type 2, name "recovery") is replaced.
The platform fragment (kernel modules for display/touch/storage/USB/charger), the DTB,
the vendor cmdline and all header values are taken unchanged from YOUR stock vendor_boot.img.

Safety nets built in:
  1. Self-test: the stock fragments are re-packed first and must be byte-identical to the
     stock image payload, otherwise the tool aborts.
  2. The result is re-unpacked and every fragment is compared with what went in.
  3. Output size is checked against the 64 MiB vendor_boot partition.

Usage:
  python3 repack_vendor_boot.py --stock vendor_boot.img --ramdisk ramdisk-recovery.cpio --out vendor_boot_twrp.img
  (--ramdisk may be a newc .cpio, or an already gzip / lz4-legacy compressed cpio)
Requires: python3, `pip install lz4`
"""
import argparse, gzip, os, shutil, struct, subprocess, sys, tempfile
import lz4.block

HERE = os.path.dirname(os.path.abspath(__file__))
PART_SIZE = 64 * 1024 * 1024
BLK = 8 * 1024 * 1024
LZ4_MAGIC = b"\x02\x21\x4c\x18"
VENDOR_CMDLINE = "bootopt=64S3,32N2,64N2"


def lz4_legacy_compress(raw: bytes) -> bytes:
    out = bytearray(LZ4_MAGIC)
    for i in range(0, len(raw), BLK):
        c = lz4.block.compress(raw[i:i + BLK], mode="high_compression",
                               compression=12, store_size=False)
        out += struct.pack("<I", len(c)) + c
    return bytes(out)


def lz4_legacy_decompress(d: bytes) -> bytes:
    assert d[:4] == LZ4_MAGIC, "not legacy lz4"
    p, res = 4, bytearray()
    while p < len(d):
        sz = struct.unpack("<I", d[p:p + 4])[0]
        p += 4
        if sz == 0x184C2102:
            continue
        res += lz4.block.decompress(d[p:p + sz], uncompressed_size=BLK)
        p += sz
    return bytes(res)


def to_cpio(data: bytes) -> bytes:
    if data[:4] == LZ4_MAGIC:
        data = lz4_legacy_decompress(data)
    elif data[:4] == b"\x04\x22\x4d\x18":          # modern lz4 frame format
        import lz4.frame
        data = lz4.frame.decompress(data)
    elif data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if data[:6] not in (b"070701", b"070702"):
        sys.exit("ERROR: --ramdisk is not a newc cpio / gzip / lz4-legacy file")
    return data


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("FAILED: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout


def mkboot(out, dtb, bootconfig, frag_platform, frag_recovery):
    run([sys.executable, os.path.join(HERE, "mkbootimg.py"),
         "--header_version", "4", "--pagesize", "0x00001000", "--base", "0x00000000",
         "--kernel_offset", "0x40080000", "--ramdisk_offset", "0x47c80000",
         "--tags_offset", "0x4bc80000", "--dtb_offset", "0x000000004bc80000",
         "--vendor_cmdline", VENDOR_CMDLINE, "--board", "",
         "--dtb", dtb, "--vendor_bootconfig", bootconfig,
         "--ramdisk_type", "platform", "--ramdisk_name", "",
         "--vendor_ramdisk_fragment", frag_platform,
         "--ramdisk_type", "recovery", "--ramdisk_name", "recovery",
         "--vendor_ramdisk_fragment", frag_recovery,
         "--vendor_boot", out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--ramdisk", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    stock = open(a.stock, "rb").read()
    if stock[:8] != b"VNDRBOOT" or struct.unpack("<I", stock[8:12])[0] != 4:
        sys.exit("ERROR: stock image is not a vendor_boot header v4")
    if len(stock) != PART_SIZE:
        print("WARNING: stock size %d != 64 MiB" % len(stock))
    if VENDOR_CMDLINE.encode() not in stock[:4096]:
        sys.exit("ERROR: stock vendor cmdline differs from the KN4 value this tool expects")

    tmp = tempfile.mkdtemp(prefix="kn4_")
    try:
        u = os.path.join(tmp, "u")
        run([sys.executable, os.path.join(HERE, "unpack_bootimg.py"),
             "--boot_img", a.stock, "--out", u])
        dtb, bc = os.path.join(u, "dtb"), os.path.join(u, "bootconfig")
        f0, f1 = os.path.join(u, "vendor_ramdisk00"), os.path.join(u, "vendor_ramdisk01")

        # 1. self-test with untouched stock fragments
        rt = os.path.join(tmp, "rt.img")
        mkboot(rt, dtb, bc, f0, f1)
        rtd = open(rt, "rb").read()
        if stock[:len(rtd)] != rtd:
            sys.exit("SELF-TEST FAILED: repack of stock fragments != stock image. Not safe to flash.")
        print("[1/3] self-test OK: stock repack is byte-identical (%d bytes)" % len(rtd))

        # build new recovery fragment
        cpio = to_cpio(open(a.ramdisk, "rb").read())
        newfrag = os.path.join(tmp, "new_recovery.lz4")
        open(newfrag, "wb").write(lz4_legacy_compress(cpio))
        assert lz4_legacy_decompress(open(newfrag, "rb").read()) == cpio
        out = os.path.join(tmp, "out.img")
        mkboot(out, dtb, bc, f0, newfrag)
        od = open(out, "rb").read()
        if len(od) > PART_SIZE:
            sys.exit("ERROR: result %d bytes exceeds the 64 MiB partition" % len(od))

        # 2. verify by unpacking the result
        u2 = os.path.join(tmp, "u2")
        run([sys.executable, os.path.join(HERE, "unpack_bootimg.py"),
             "--boot_img", out, "--out", u2])
        rd = lambda p: open(p, "rb").read()
        assert rd(os.path.join(u2, "vendor_ramdisk00")) == rd(f0), "platform fragment changed!"
        assert rd(os.path.join(u2, "dtb")) == rd(dtb), "dtb changed!"
        assert lz4_legacy_decompress(rd(os.path.join(u2, "vendor_ramdisk01"))) == cpio, \
            "recovery fragment mismatch"
        print("[2/3] verify OK: platform fragment + dtb untouched, recovery fragment == TWRP ramdisk")

        open(a.out, "wb").write(od + b"\0" * (PART_SIZE - len(od)))
        print("[3/3] wrote %s (%d bytes padded to 64 MiB; payload %d bytes, %.1f MiB headroom)"
              % (a.out, PART_SIZE, len(od), (PART_SIZE - len(od)) / 1048576))
        print("NOTE: the AVB footer is not re-signed -> flash vbmeta with verification disabled.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
