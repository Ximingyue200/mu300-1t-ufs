#!/usr/bin/env python3
"""Turn a MU300 desktop package (k7.2.8) into one that installs on the 1 TB UFS U30 Air.

    python repackage.py  PACKAGE.zip  --boot BOOT.img  --modules MODULES_DIR  --out OUT.zip

What it changes (see docs/package-adapt.md for why):

  1. payload/boot-linux.img      the UFS-capable mainline 7.2.8 boot image (built for this device)
  2. payload/mu300-openwrt.tar.gz
                                 lib/modules/7.2.8 replaced with the modules built for that kernel
  3. payload/rootfs.requirements a size that covers two copies plus the modules
  4. desktop/update_control.py   UFS region layout: /dev/loop*|/dev/sd* is "part", and on that layout the
                                 packaged boot image is used as is (the desktop "part" segment does not boot
                                 a raw region behind the last partition)
  5. desktop/mu300-update-library.sh, desktop/local-update.sh
                                 the release's LuCI system is a directory of its own (openwrt-luci)

Every checksum the package verifies (payload.sha256, boot-linux.sha256, desktop/manifest.json) is updated.
The result passes `OpenWrt-Installer.exe --check` ("MU300 desktop package verified").

Only the module *files* and the boot image come from a build of the UFS patch; the patch itself is
patches/0022-ufs-sprd-accept-the-firmware-dt.patch plus the three CONFIG_ lines in config/ufs.config.
"""
import argparse
import glob
import hashlib
import io
import json
import os
import tarfile
import time
import zipfile

MODULE_TREE = "./lib/modules/7.2.8"
REQUIREMENTS = b"800000 40000\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_update_control(data):
    text = data.decode()
    edits = [
        # the UFS layout: a raw region behind the last partition, mounted through a loop
        ('    case "$d" in /dev/mmcblk[1-9]*) echo sd ;; *) echo legacy ;; esac',
         '    case "$d" in /dev/mmcblk[1-9]*) echo sd ;; /dev/sd*|/dev/loop*) echo part ;; *) echo legacy ;; esac'),
        # the region flag needs the disk device: it becomes the fifth line the probe prints
        ("cat /run/mu300/misc-dev\nif [ -s /etc/mu300/desktop-mode ]",
         "cat /run/mu300/misc-dev\nif [ -s /etc/mu300/desktop-mode ]"),
        ("fi'''", "fi\ncat /run/mu300/disk-dev'''"),
        ("len(info) != 4", "len(info) != 5"),
        ("""        layout = legacy_layout(client, root, execute, read_exact) if mode == 'legacy' else None""",
         """        layout = legacy_layout(client, root, execute, read_exact) if mode == 'legacy' else None
        # a UFS unit keeps its OpenWrt in a raw region behind the last partition; the desktop boot image's
        # "part" segment expects a GPT partition, so the package's own boot image is written unchanged
        region = mode == 'part' and info[4].startswith(('/dev/loop', '/dev/sd'))"""),
        ("""        newboot = api['boot'](root, module, mode, live, slot)""",
         """        newboot = (api['payload_file'](root, 'boot-linux.img').read_bytes() if region
                   else api['boot'](root, module, mode, live, slot))"""),
    ]
    for old, new in edits:
        if old not in text:
            if old == new:
                continue
            raise SystemExit("update_control.py: anchor not found: " + old[:60])
        text = text.replace(old, new, 1)
    return text.encode()


def patch_library(data):
    text = data.decode()
    edits = [
        ("running_os() { [ -e /etc/openwrt_release ] && echo openwrt || echo ubuntu; }",
         "running_os() {\n"
         "    # the release ships the LuCI variant as its own system directory (openwrt-luci)\n"
         "    [ -e /etc/openwrt_release ] || { echo ubuntu; return; }\n"
         "    if [ -d \"$DISK/openwrt-luci\" ] && [ / -ef \"$DISK/openwrt-luci\" ]; then echo openwrt-luci\n"
         "    elif [ -d \"$DISK/openwrt\" ] && [ / -ef \"$DISK/openwrt\" ]; then echo openwrt\n"
         "    else echo openwrt; fi\n"
         "}"),
        ("    for os in ubuntu openwrt; do\n        [ -d \"$DISK/$os\" ] && printf '%s ' \"$os\"",
         "    for os in ubuntu openwrt openwrt-luci; do\n        [ -d \"$DISK/$os\" ] && printf '%s ' \"$os\""),
        ('    [ -d "$DISK/ubuntu" ] || [ -d "$DISK/openwrt" ] || die "the Linux partition is not mounted at $DISK"',
         '    [ -d "$DISK/ubuntu" ] || [ -d "$DISK/openwrt" ] || [ -d "$DISK/openwrt-luci" ] || die "the Linux partition is not mounted at $DISK"'),
        ('        openwrt) echo "etc/config etc/mu300', '        openwrt|openwrt-luci) echo "etc/config etc/mu300'),
        ('        openwrt) echo "opt/mu300/android lib/firmware lib/modules" ;;',
         '        openwrt|openwrt-luci) echo "opt/mu300/android lib/firmware lib/modules" ;;'),
        ('        case $os in ubuntu|openwrt) ;; *) die "unknown system \'$os\'" ;; esac',
         '        case $os in ubuntu|openwrt|openwrt-luci) ;; *) die "unknown system \'$os\'" ;; esac'),
    ]
    for old, new in edits:
        if old not in text:
            raise SystemExit("mu300-update-library.sh: anchor not found: " + old[:60])
        text = text.replace(old, new, 1)
    return text.encode()


def patch_local_update(data):
    text = data.decode()
    edits = [
        ("""STAGE=$payload
if ! apply_one openwrt desktop-local; then exit 1; fi
swapped=1
(cd "$DISK/openwrt" && sha256sum -c "$payload/rootfs-critical.sha256")
[ -s "$DISK/openwrt/lib/firmware/wcnmodem.bin" ] && [ -x "$DISK/openwrt/opt/mu300/android/vendor/bin/modem_control" ]""",
         """STAGE=$payload
# the name of the installed system (the release ships the LuCI variant as openwrt-luci)
os=
for c in openwrt-luci openwrt; do [ -d "$DISK/$c" ] && [ ! -L "$DISK/$c" ] && os=$c && break; done
[ -n "$os" ] || { echo 'no OpenWrt system found on the Linux partition'; exit 1; }
[ -f "$payload/$(rootfs_asset "$os")" ] || ln -sf "$payload/mu300-openwrt-rootfs.tar.gz" "$payload/$(rootfs_asset "$os")"
if ! apply_one "$os" desktop-local; then exit 1; fi
swapped=1
(cd "$DISK/$os" && sha256sum -c "$payload/rootfs-critical.sha256")
[ -s "$DISK/$os/lib/firmware/wcnmodem.bin" ] && [ -x "$DISK/$os/opt/mu300/android/vendor/bin/modem_control" ]"""),
        ("""            mv "$DISK/openwrt" "$DISK/openwrt.failed.$$" && mv "$DISK/openwrt.old" "$DISK/openwrt" || echo 'ROOT RESTORE FAILED' """,
         """            mv "$DISK/${os:-openwrt}" "$DISK/${os:-openwrt}.failed.$$" && mv "$DISK/${os:-openwrt}.old" "$DISK/${os:-openwrt}" || echo 'ROOT RESTORE FAILED' """),
        ('echo linux > "$DISK/openwrt/etc/mu300/default-boot"', 'echo linux > "$DISK/$os/etc/mu300/default-boot"'),
        ('echo openwrt > "$DISK/.mu300/boot-os"', 'echo "$os" > "$DISK/.mu300/boot-os"'),
    ]
    for old, new in edits:
        if old not in text:
            if old.rstrip() + " " == new:  # tolerate a trailing-space difference
                continue
            raise SystemExit("local-update.sh: anchor not found: " + old[:60])
        text = text.replace(old, new, 1)
    text = text.replace('$DISK/openwrt', '$DISK/${os:-openwrt}')
    return text.encode()


def new_rootfs(old_bytes, modules):
    buf = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=io.BytesIO(old_bytes)) as tin, \
            tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tout:
        for m in tin:
            if m.name == MODULE_TREE or m.name.startswith(MODULE_TREE + "/"):
                continue
            tout.addfile(m, tin.extractfile(m) if m.isfile() else None)
        d = tarfile.TarInfo(MODULE_TREE)
        d.type = tarfile.DIRTYPE
        d.mode = 0o755
        d.mtime = now
        d.uid = d.gid = 0
        tout.addfile(d)
        for ko in sorted(glob.glob(os.path.join(modules, "*.ko"))):
            ti = tarfile.TarInfo(MODULE_TREE + "/" + os.path.basename(ko))
            ti.size = os.path.getsize(ko)
            ti.mode = 0o644
            ti.mtime = now
            ti.uid = ti.gid = 0
            with open(ko, "rb") as fh:
                tout.addfile(ti, fh)
        for extra in ("modules.builtin", "modules.builtin.modinfo", "modules.in-tree"):
            p = os.path.join(os.path.dirname(os.path.abspath(modules)), extra)
            if not os.path.exists(p):
                continue
            ti = tarfile.TarInfo(MODULE_TREE + "/" + extra)
            ti.size = os.path.getsize(p)
            ti.mode = 0o644
            ti.mtime = now
            ti.uid = ti.gid = 0
            with open(p, "rb") as fh:
                tout.addfile(ti, fh)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--boot", required=True, help="UFS-capable 7.2.8 boot image (64 MiB, header v4)")
    ap.add_argument("--modules", required=True, help="flat module directory from the same kernel build")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    zin = zipfile.ZipFile(a.package)
    boot = open(a.boot, "rb").read()
    if len(boot) != 64 << 20 or boot[:8] != b"ANDROID!" or boot[-64:-60] != b"AVBf":
        raise SystemExit("--boot: not a 64 MiB Android boot v4 image with an AVB footer")
    rootfs = new_rootfs(zin.read("payload/mu300-openwrt.tar.gz"), a.modules)
    files = {
        "payload/boot-linux.img": boot,
        "payload/boot-linux.sha256": (sha(boot) + "\n").encode(),
        "payload/mu300-openwrt.tar.gz": rootfs,
        "payload/rootfs.requirements": REQUIREMENTS,
        "desktop/update_control.py": patch_update_control(zin.read("desktop/update_control.py")),
        "desktop/mu300-update-library.sh": patch_library(zin.read("desktop/mu300-update-library.sh")),
        "desktop/local-update.sh": patch_local_update(zin.read("desktop/local-update.sh")),
    }
    lines = []
    for line in zin.read("payload/payload.sha256").decode().splitlines():
        p = line.split(None, 1)
        name = p[1].strip() if len(p) == 2 else ""
        if name in ("boot-linux.img", "mu300-openwrt.tar.gz", "rootfs.requirements"):
            lines.append(f"{sha(files['payload/' + name])}  {name}")
        elif line.strip():
            lines.append(line)
    files["payload/payload.sha256"] = ("\n".join(lines) + "\n").encode()

    m = json.loads(zin.read("desktop/manifest.json"))
    for table in ("magisk", "desktop"):
        d = m.get(table) or {}
        for name, data in files.items():
            if name in d:
                d[name] = sha(data)
    files["desktop/manifest.json"] = (json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode()

    with zipfile.ZipFile(a.out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
        for info in zin.infolist():
            data = files.get(info.filename)
            if data is None:
                data = zin.read(info.filename)
            ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            ni.compress_type = zipfile.ZIP_DEFLATED
            ni.external_attr = info.external_attr
            ni.create_system = info.create_system
            zout.writestr(ni, data)
    print("wrote", a.out, os.path.getsize(a.out))


if __name__ == "__main__":
    main()
