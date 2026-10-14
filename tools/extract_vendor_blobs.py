#!/usr/bin/env python3
"""
extract_vendor_blobs.py  (phase 2: TWRP /data decryption files for TECNO KN4 / Spark 50)

Runs on YOUR PC against YOUR OWN stock_super.img backup. Nothing is uploaded anywhere.
It cuts the logical partition `vendor_<slot>` out of super, extracts it, and keeps ONLY what TWRP needs to
unlock FBE with the Trustonic TEE: keymint / gatekeeper / secureclock / sharedsecret / tee services, their rc +
vintf files, the trustlets in mcRegistry and the shared libraries they depend on (ELF dependency closure).
Result: kn4_vendor_blobs.zip (small). No /data, no personal data, no IMEI/serials are involved.

Use inside Windows WSL (Ubuntu) or any Linux:
    sudo apt update && sudo apt install -y erofs-utils python3
    cd ~                                   # IMPORTANT: work in the Linux home, NOT under /mnt/c (NTFS breaks symlinks)
    cp "/mnt/c/Users/<you>/.../extract_vendor_blobs.py" .
    python3 extract_vendor_blobs.py --super "/mnt/c/Users/<you>/.../stock_super.img"
(in WSL your C: drive is /mnt/c). Needs ~3 GB free disk in the work dir; the work dir is deleted afterwards.
Result: ~/kn4_vendor_blobs.zip  -> copy it back with:  cp ~/kn4_vendor_blobs.zip /mnt/c/Users/<you>/Desktop/
"""
import argparse, hashlib, os, re, shutil, struct, subprocess, sys, zipfile

SECTOR = 512
WANT = re.compile(r"(trustonic|mobicore|mcdriver|kinibi|tbase|t-base|(^|[._/-])tee|libtee|tee[._-]|keymint|keymaster|"
                  r"gatekeeper|weaver|secureclock|sharedsecret|remotelyprovisioned|boot-service|bootctrl|fastboot|"
                  r"plpath|libmc|libkm|libgk|mtk_bsg|libsecmem|teei|utee|cryptfs|vold)", re.I)
SKIP_LIBS = re.compile(r"^(libc|libm|libdl|liblog|libc\+\+|ld-android|libvndksupport|libnativewindow|libandroid)\.so$")


def die(msg):
    sys.exit("ERROR: " + msg)


def parse_lp(f):
    f.seek(4096)
    g = f.read(52)
    magic, ssz, _ck, max_size, slots, lbs = struct.unpack("<II32sIII", g)
    if magic != 0x616C4467:
        die("not a raw super image (no LP geometry at 4096). Is this a sparse image? Dump it raw with mtkclient.")
    parts = {}
    for slot in range(slots):
        off = 4096 + 2 * 4096 + slot * max_size
        f.seek(off)
        h = f.read(256)
        (hmagic, major, minor, hsize) = struct.unpack("<IHHI", h[:12])
        if hmagic != 0x414C5030:
            continue
        # tables_size at 44, partitions/extents descriptors at 80..
        poff, pnum, psz = struct.unpack("<III", h[80:92])
        eoff, enum, esz = struct.unpack("<III", h[92:104])
        f.seek(off + hsize)
        tables = f.read(struct.unpack("<I", h[44:48])[0])
        pdict = {}
        for i in range(pnum):
            e = tables[poff + i * psz: poff + (i + 1) * psz]
            name = e[:36].split(b"\0")[0].decode()
            attrs, first, n, grp = struct.unpack("<IIII", e[36:52])
            ext = []
            for k in range(first, first + n):
                x = tables[eoff + k * esz: eoff + (k + 1) * esz]
                ns, ttype, tdata, tsrc = struct.unpack("<QIQI", x[:24])
                ext.append((ns, ttype, tdata))
            pdict[name] = ext
        parts[slot] = pdict
    if not parts:
        die("no valid LP metadata found")
    return parts


def carve(super_path, ext, out):
    done = 0
    with open(super_path, "rb") as f, open(out, "wb") as o:
        for ns, ttype, tdata in ext:
            if ttype == 1:                          # zero extent
                o.write(b"\0" * (ns * SECTOR))
            else:
                f.seek(tdata * SECTOR)
                left = ns * SECTOR
                while left:
                    b = f.read(min(left, 16 << 20))
                    if not b:
                        die("super image is truncated")
                    o.write(b)
                    left -= len(b)
            done += ns * SECTOR
    return done


def elf_needed(path):
    try:
        d = open(path, "rb").read()
        if d[:4] != b"\x7fELF" or d[4] != 2:
            return []
        shoff = struct.unpack("<Q", d[0x28:0x30])[0]
        shentsize, shnum = struct.unpack("<HH", d[0x3A:0x3E])
        secs = [struct.unpack("<IIQQQQIIQQ", d[shoff + i * shentsize: shoff + i * shentsize + 64]) for i in range(shnum)]
        res = []
        for s in secs:
            if s[1] == 6:
                so = secs[s[6]][4]
                for k in range(s[5] // 16):
                    tag, val = struct.unpack("<qQ", d[s[4] + k * 16: s[4] + k * 16 + 16])
                    if tag == 1:
                        res.append(d[so + val: d.index(b"\0", so + val)].decode())
        return res
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--super", required=True)
    ap.add_argument("--slot", default="a")
    ap.add_argument("--work", default="kn4_work")
    ap.add_argument("--out", default="kn4_vendor_blobs")
    ap.add_argument("--keep-work", action="store_true")
    a = ap.parse_args()
    if not shutil.which("fsck.erofs"):
        die("fsck.erofs not found. In WSL/Ubuntu: sudo apt install erofs-utils")
    os.makedirs(a.work, exist_ok=True)

    with open(a.super, "rb") as f:
        parts = parse_lp(f)
    want = "vendor_" + a.slot
    meta = parts[0 if a.slot == "a" else min(1, len(parts) - 1)]
    print("logical partitions in super (slot %s metadata): %s" % (a.slot, ", ".join(sorted(meta))))
    if want not in meta:
        die("%s not found in super" % want)
    img = os.path.join(a.work, want + ".img")
    n = carve(a.super, meta[want], img)
    print("carved %s: %.1f MiB" % (want, n / 1048576))
    with open(img, "rb") as f:
        f.seek(1024)
        if struct.unpack("<I", f.read(4))[0] != 0xE0F5E1E2:
            die("%s is not EROFS (unexpected). Send me the output of `file %s`." % (want, img))

    root = os.path.join(a.work, "vendor_x")
    shutil.rmtree(root, ignore_errors=True)
    print("extracting EROFS (this can take a few minutes)...")
    r = subprocess.run(["fsck.erofs", "--extract=" + root, "--overwrite", img], capture_output=True, text=True)
    open(os.path.join(a.work, "fsck_erofs.log"), "w").write(r.stdout + "\n" + r.stderr)
    if not os.path.isdir(root) or not os.listdir(root):
        die("extraction failed; see %s/fsck_erofs.log and send me its last lines" % a.work)
    if r.returncode:
        print("WARNING: fsck.erofs returned %d (continuing; see log). Last line: %s" %
              (r.returncode, (r.stderr or r.stdout).strip().splitlines()[-1:] or ""))

    # ---------- selection
    sel = set()

    def add(rel):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            sel.add(os.path.normpath(rel))

    for d in ("bin", "bin/hw", "lib64", "lib64/hw"):
        base = os.path.join(root, d)
        if os.path.isdir(base):
            for fn in os.listdir(base):
                if WANT.search(fn):
                    add(os.path.join(d, fn))
    rc_hits = []
    for rcdir in ("etc/init", "etc/init/hw"):
        base = os.path.join(root, rcdir)
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            p = os.path.join(base, fn)
            if not (os.path.isfile(p) and fn.endswith(".rc")):
                continue
            txt = open(p, errors="replace").read()
            hit = False
            for m in re.finditer(r"^service\s+(\S+)\s+(/vendor/\S+)", txt, re.M):
                if WANT.search(m.group(1)) or WANT.search(m.group(2)):
                    add(m.group(2).replace("/vendor/", "", 1))
                    hit = True
            if hit or WANT.search(fn):
                add(os.path.join(rcdir, fn))
                rc_hits.append(fn)
    for d in ("etc/vintf", "app/mcRegistry", "thh", "tee"):
        base = os.path.join(root, d)
        if os.path.isdir(base):
            for dp, _, fs in os.walk(base):
                for fn in fs:
                    add(os.path.relpath(os.path.join(dp, fn), root))
    for fn in os.listdir(os.path.join(root, "etc")) if os.path.isdir(os.path.join(root, "etc")) else []:
        if fn.startswith("fstab"):
            add(os.path.join("etc", fn))

    libnames = {}
    for d in ("lib64", "lib64/hw"):
        base = os.path.join(root, d)
        if os.path.isdir(base):
            for fn in os.listdir(base):
                libnames.setdefault(fn, os.path.join(d, fn))
    for _ in range(12):                                   # dependency closure inside vendor
        new = set()
        for rel in list(sel):
            for dep in elf_needed(os.path.join(root, rel)):
                if SKIP_LIBS.match(dep):
                    continue
                if dep in libnames and os.path.normpath(libnames[dep]) not in sel:
                    new.add(os.path.normpath(libnames[dep]))
        if not new:
            break
        sel |= new

    out = a.out
    shutil.rmtree(out, ignore_errors=True)
    lines = []
    for rel in sorted(sel):
        src = os.path.join(root, rel)
        dst = os.path.join(out, "vendor", rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        lines.append("%s  %9d  /vendor/%s" % (hashlib.sha256(open(dst, "rb").read()).hexdigest(),
                                                 os.path.getsize(dst), rel.replace(os.sep, "/")))
    open(os.path.join(out, "MANIFEST.txt"), "w").write("\n".join(lines) + "\n\nrc files with matching services: %s\n"
                                                         % ", ".join(sorted(rc_hits)))
    z = out + ".zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for dp, _, fs in os.walk(out):
            for fn in fs:
                p = os.path.join(dp, fn)
                zf.write(p, os.path.relpath(p, os.path.dirname(out) or "."))
    print("selected %d files -> %s (%.1f MB)" % (len(sel), z, os.path.getsize(z) / 1048576))
    if not a.keep_work:
        shutil.rmtree(a.work, ignore_errors=True)
    print("Done. Upload %s." % z)


if __name__ == "__main__":
    main()
