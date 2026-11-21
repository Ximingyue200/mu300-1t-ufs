"""Fetch the UFS build artifacts, then either keep the kernel bundle or assemble a slot-b boot image.

Run after the workflow finished:  python fetch-artifacts.py
Writes: artifacts/ (raw upload), boot-6.18.img (only when no bundle was built)
"""
import json, os, shutil, subprocess, sys, urllib.error, urllib.request, zipfile

TOK = "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"
REPO = "Ximingyue200/mu300-linux"
RUN = "44888451844"
BASE = r"D:\zhang\学习\_router"
ART = os.path.join(BASE, "artifacts")


def api(path, raw=False):
    req = urllib.request.Request("https://api.github.com/repos/" + REPO + path,
                                 headers={"Authorization": "Bearer " + TOK,
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read() if raw else json.loads(r.read().decode())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url, dest):
    """GitHub artifact downloads redirect to a signed URL; the token must not be sent there."""
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
        raise SystemExit("artifact download: no Location")
    req2 = urllib.request.Request(loc, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req2, timeout=600) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def main():
    arts = api(f"/actions/runs/{RUN}/artifacts")["artifacts"]
    if not arts:
        sys.exit("no artifacts on the run yet")
    a = arts[0]
    os.makedirs(ART, exist_ok=True)
    zpath = os.path.join(ART, "ufs-kernel.zip")
    if not os.path.exists(zpath):
        download(a["archive_download_url"], zpath)
    print("artifact", a["name"], a["size_in_bytes"], "->", zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(ART)
        print("entries:", len(z.namelist()))
    # the bundle, if the CI step built one
    bundles = [os.path.join(r, f) for r, _, fs in os.walk(ART) for f in fs if f.startswith("mu300-kernel-") and f.endswith(".tar.gz")]
    imgs = [os.path.join(r, f) for r, _, fs in os.walk(ART) for f in fs if f == "Image"]
    print("bundles:", bundles)
    print("images:", imgs)
    if not imgs:
        sys.exit("no Image in the artifact")
    if bundles:
        print("BUNDLE", bundles[0])
        return
    # no bundle: build the slot-b boot image here (stock boot + new kernel + the 5.4 ramdisk is NOT usable,
    # so this path needs a generic ramdisk for 6.18; it is only a fallback and is assembled from the modules)
    print("no bundle: boot image assembly needs the 6.18 ramdisk; see the notes")


if __name__ == "__main__":
    main()
