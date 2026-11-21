"""Download a finished UFS-build run and assemble the kernel bundle the device installs.

    python build-bundle.py RUN_ID KERNEL_RELEASE [series]

RUN_ID          the Actions run (UFS kernel build)
KERNEL_RELEASE  what uname -r prints, e.g. 6.18.60 (the modules directory is named after it)
series          bundle asset name suffix, default the kernel's major.minor (6.18, 7.2)

Writes <_router>/artifacts-<run>/ and <_router>/out/mu300-kernel-<series>.tar.gz.
The metadata files are written as bytes: a CRLF kernel.release would name the modules directory
"<release>\r" and then no module loads.
"""
import glob, json, os, shutil, sys, tarfile, urllib.error, urllib.request, zipfile

TOK = "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"
REPO = "Ximingyue200/mu300-linux"
BASE = r"D:\zhang\学习\_router"
LIB = os.path.join(BASE, "pylibs")
SRC = os.path.join(BASE, "mu300-linux")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path):
    req = urllib.request.Request("https://api.github.com/repos/" + REPO + path,
                                 headers={"Authorization": "Bearer " + TOK,
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def download(url, dest):
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOK,
                                               "Accept": "application/vnd.github+json",
                                               "User-Agent": "curl/8"})
    loc = None
    try:
        opener.open(req, timeout=120)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location")
    if not loc:
        raise SystemExit("no redirect for " + url)
    with urllib.request.urlopen(urllib.request.Request(loc, headers={"User-Agent": "curl/8"}), timeout=600) as r, \
            open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def main():
    run, krel = sys.argv[1], sys.argv[2]
    series = sys.argv[3] if len(sys.argv) > 3 else ".".join(krel.split(".")[:2])
    art = os.path.join(BASE, f"artifacts-{run}")
    os.makedirs(art, exist_ok=True)
    zpath = os.path.join(art, "ufs-kernel.zip")
    if not os.path.exists(zpath):
        arts = api(f"/actions/runs/{run}/artifacts")["artifacts"]
        if not arts:
            raise SystemExit("run has no artifacts")
        download(arts[0]["archive_download_url"], zpath)
        print("downloaded", arts[0]["name"], arts[0]["size_in_bytes"])
    with zipfile.ZipFile(zpath) as z:
        z.extractall(art)
    outdir = os.path.join(art, "upstream", "out")
    image = os.path.join(outdir, "Image")
    mods = os.path.join(outdir, "modules")
    if not (os.path.exists(image) and os.path.isdir(mods)):
        raise SystemExit("artifact has no Image/modules")
    stage = os.path.join(BASE, f"bundle-{series}")
    os.makedirs(os.path.join(stage, "modules"), exist_ok=True)
    # LK needs the 0x180000 stub
    subprocess = __import__("subprocess")
    subprocess.run([sys.executable, os.path.join(SRC, "upstream", "wrap-image.py"), image,
                    os.path.join(stage, "Image")], check=True)
    env = dict(os.environ, PYTHONPATH=LIB)
    subprocess.run([sys.executable, os.path.join(SRC, "boot", "build-boot-image.py"), "--generic-ramdisk",
                    "--modules", mods, "--module-order", os.path.join(SRC, "upstream", "module-order.txt"),
                    "--busybox", os.path.join(BASE, "mu300-linux", "work", "ref", "busybox"),
                    "--logdw", os.path.join(BASE, "mu300-linux", "work", "ref", "logdw"),
                    "--e2fsck", os.path.join(BASE, "mu300-linux", "work", "ref", "e2fsck"),
                    "--ueventd-perms", os.path.join(SRC, "android-vendor", "ueventd-perms.sh"),
                    "--out", os.path.join(stage, "ramdisk-generic.lz4")], check=True, env=env)
    for ko in glob.glob(os.path.join(mods, "*.ko")):
        shutil.copyfile(ko, os.path.join(stage, "modules", os.path.basename(ko)))
    for f in ("modules.builtin", "modules.builtin.modinfo", "modules.in-tree"):
        p = os.path.join(outdir, f)
        if os.path.exists(p):
            shutil.copyfile(p, os.path.join(stage, f))
    for name, text in (("kernel.release", krel), ("devices", "f50 u30air"),
                       ("features", "sdcard\nlinux-slot\ngpt-root")):
        with open(os.path.join(stage, name), "wb") as f:
            f.write((text + "\n").encode("ascii"))
    out = os.path.join(BASE, "out", f"mu300-kernel-{series}.tar.gz")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    entries = ["Image", "ramdisk-generic.lz4", "ramdisk-generic.json", "kernel.release", "devices", "features",
               "modules.builtin", "modules.builtin.modinfo", "modules.in-tree"]
    with tarfile.open(out, "w:gz", compresslevel=6) as t:
        for e in entries:
            p = os.path.join(stage, e)
            if os.path.exists(p):
                t.add(p, arcname="./" + e)
        t.add(os.path.join(stage, "modules"), arcname="./modules")
    print("bundle:", out, os.path.getsize(out))


if __name__ == "__main__":
    main()
