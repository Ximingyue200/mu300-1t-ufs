# ZTE U30 Air 1 TB (UFS) — mainline Linux / OpenWrt port

Everything needed to run **mainline Linux (6.18 / 7.2) with OpenWrt** on the UFS variant of the
ZTE U30 Air (`ums9620_2h10_feimao`, Samsung KLUGGARHGB-B0E1, `/dev/sda`, 4096-byte logical blocks),
including the desktop firmware package used for it.

Upstream: [dikeckaan/mu300-linux](https://github.com/dikeckaan/mu300-linux) · issue
[#396](https://github.com/dikeckaan/mu300-linux/issues/396) · PR
[#504](https://github.com/dikeckaan/mu300-linux/pull/504)

## What the unit needed

The eMMC variants work out of the box; a UFS unit does not, because the firmware's own device tree
(the one LK passes to the kernel) names the controller differently than the port's own DTS:

| | firmware DT | mainline `ufs-sprd` expects |
|---|---|---|
| compatible | `sprd,ufshc` | `sprd,ums9620-ufs` |
| resets | `ufs_soft_rst`, `ufsdev_soft_rst` | `controller`, `device` |
| syscons | `(phandle, reg, mask)` triples (`phy_sram_*`, `aon_apb_ufs_clk_en`, …) | phandles named `sprd,ufs-anlg-syscon`, `sprd,aon-apb-syscon` |
| host driver | — | disabled altogether (`drivers/ufs` is excluded from the build) |

## Kernel

* `patches/0022-ufs-sprd-accept-the-firmware-dt.patch` — teaches `ufs-sprd` the firmware's names
  (match `sprd,ufshc`, reset fallbacks, syscon from the triples). Applies to 6.18 and 7.2.
* `config/ufs.config` — `CONFIG_SCSI_UFSHCD`, `CONFIG_SCSI_UFSHCD_PLATFORM`, `CONFIG_SCSI_UFS_SPRD`
  (append to `upstream/mu300-mainline.config`; `ARCH_SPRD` is already on).

Nothing is changed in the device tree, in `vendor_boot` or in any partition.

Build with the port's own pipeline (`upstream/Dockerfile` + `build.sh` + `build-modules.sh`) on an
arm64 runner; `scripts/build-bundle.py` downloads such a run and assembles the kernel bundle
`mu300-update` installs (`Image`, `ramdisk-generic.lz4`, `modules/`, `kernel.release`, `devices`, `features`).

> `kernel.release` must be LF-only. A CRLF (Windows checkout) names the modules directory
> `<release>\r` and then no module loads.

Verified on the unit: 6.18.60 and 7.2.8 boot with `ufshcd-sprd 22000000.ufs`, `scsi host0: ufshcd`,
`/dev/sda` and the ext4 region on it, Wi-Fi AP, mobile data (SIM2) and LuCI.

## Firmware package

`scripts/repackage.py` turns the vendor's `…-k7.2.8.zip` into one that installs on the UFS unit:

1. the boot image gets the UFS-capable 7.2.8 kernel (a 64 MiB Android boot v4 image, built for this device);
2. `lib/modules/7.2.8` in the rootfs is replaced by the modules of that same build — the package's own
   206 modules come from a build with a different `struct module` size and refuse to load
   (`.gnu.linkonce.this_module section size must match`);
3. `desktop/update_control.py`: the UFS layout is a raw region behind the last partition behind a loop
   (`/dev/loop0`), not a GPT partition — it is treated as `part`, and on that layout the packaged boot
   image is written as is (a desktop "part" boot image does not boot there);
4. `desktop/mu300-update-library.sh` + `desktop/local-update.sh`: the release's LuCI system lives in a
   directory of its own, `openwrt-luci`, not `openwrt`.

```sh
python scripts/repackage.py mu300-openwrt-…-k7.2.8.zip \
    --boot boot-linux-7.2.8-ufs.img --modules bundle-7.2/modules \
    --out mu300-openwrt-…-k7.2.8-ufs.zip
```

The result passes the package's own check (`OpenWrt-Installer.exe --check`, "kernel 7.2") and was
installed on the unit end to end: the device comes back with OpenWrt 25.12.5 (`mu300-r20261120…`),
kernel 7.2.8, UFS root, Wi-Fi AP, mobile data and LuCI at `192.168.77.1`.

Installing over SSH: the package's CLI entry has a relative-import bug (`desktop/update_control.py`
loaded as a top-level module). `scripts/run_update.py` loads it with the backend package context, the
way the GUI does, and lets the package update a running system:

```sh
MU300_SSH_PASSWORD=yourpassword python scripts/run_update.py <package-dir> <device-ip>
```

## Notes from the field

* Android and the partition table are never touched; the UFS install keeps Android's userdata (online
  F2FS shrink) and an `openwrt-luci.old` copy of the previous system.
* Keep the kernel at 7.2/6.18 **with this patch** — a build without it cannot see the UFS at all.
* LAN after the package install: `192.168.77.1` (the package's default), not the installer's `192.168.78.1`.

More detail: [`docs/ports-notes.md`](docs/ports-notes.md), [`docs/package-adapt.md`](docs/package-adapt.md).
