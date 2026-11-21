#!/usr/bin/env python3
"""Update a running MU300 device from a desktop package directory.

    MU300_SSH_PASSWORD=<root password> python run_update.py PACKAGE_DIR DEVICE_IP

The package's own CLI entry (`OpenWrt-Installer.py --update`) loads `desktop/update_control.py` as a
top-level module, which breaks its `from .ssh_runtime import connect_ssh`. The GUI loads the same file
inside the backend package instead. This driver does the same: it gives the module the backend package
context and calls `update_mu300` unchanged.

Needs: paramiko (and, only when the package builds a boot image, the `lz4` module).
"""
import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

PKG = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
if PKG is None or not (PKG / "desktop" / "installer.py").is_file():
    raise SystemExit(__doc__)

# keep every temporary file beside the package; a failed cleanup must not abort the update
tempfile.tempdir = str(PKG / "work" / "tmp")
(PKG / "work" / "tmp").mkdir(parents=True, exist_ok=True)
_cleanup = tempfile.TemporaryDirectory.cleanup


def _safe_cleanup(self):
    try:
        _cleanup(self)
    except Exception as exc:  # leftovers are harmless
        print("temp cleanup skipped:", exc, flush=True)


tempfile.TemporaryDirectory.cleanup = _safe_cleanup

sys.path.insert(0, str(PKG))
spec = importlib.util.spec_from_file_location("installer", PKG / "desktop" / "installer.py")
installer = importlib.util.module_from_spec(spec)
sys.modules["installer"] = installer
spec.loader.exec_module(installer)

import backend  # noqa: E402  (the package's backend package, for backend.ssh_runtime)

spec = importlib.util.spec_from_file_location("backend.payload_update", PKG / "desktop" / "update_control.py")
control = importlib.util.module_from_spec(spec)
sys.modules["backend.payload_update"] = control
spec.loader.exec_module(control)

manifest = installer.verify(PKG)
print("package verified; kernel", manifest["kernel"])

ap = argparse.ArgumentParser()
ap.add_argument("package")
ap.add_argument("host")
args = ap.parse_args()
result = control.update_mu300(dict(installer.__dict__), argparse.Namespace(host=args.host), PKG)
print("RESULT:", getattr(result, "state", ""), "|", getattr(result, "message", ""))
