# U30 Air 1TB UFS × 主线内核 移植记录

日期：2026-11-21 · 设备：`ums9620_2h10_feimao` / Samsung KLUGGARHGB-B0E1 1TB UFS / `/dev/sda` / 4096 字节逻辑块

## 结论

主线内核 **6.18.60** 已在这台 1TB UFS 上跑通：UFS 能枚举、根文件系统在 UFS 上、WiFi / 移动数据 / LuCI 全部正常。
**没有改 vendor_boot，也没有改设备树**——只改驱动让它接受厂商固件自己的 DT。

## 问题拆解

| 层 | 厂商固件（Android 13） | 主线（6.18/7.2） | 处理方式 |
|---|---|---|---|
| 存储控制器 | `/dev/sda`（UFS，4K 逻辑块） | 内核配置里 `drivers/ufs` 被排除，无驱动 | 打开 `CONFIG_SCSI_UFSHCD(_PLATFORM)` + `CONFIG_SCSI_UFS_SPRD` |
| 驱动匹配 | DT: `compatible = "sprd,ufshc"` | 只认 `sprd,ums9620-ufs` | match 表加 `sprd,ufshc` |
| 复位 | `ufs_soft_rst` / `ufsdev_soft_rst` | 要 `controller` / `device` | 驱动内回退映射 |
| syscon | `(phandle, reg, mask)` 三元组：`phy_sram_*`、`aon_apb_ufs_clk_en`、`ufsdev_refclk_en` | 要具名 phandle：`sprd,ufs-anlg-syscon`、`sprd,aon-apb-syscon` | 从三元组里取 phandle 回退 |

补丁：`upstream/patches/0022-ufs-sprd-accept-the-firmware-dt.patch`（fork commit `8b19031`）
配置：`upstream/mu300-mainline.config` 追加三个选项（fork commit `3d56a10`）

## 构建

fork（`Ximingyue200/mu300-linux`）加了 `.github/workflows/ufs-build.yml`：
arm64 runner → `upstream/Dockerfile` → `build.sh`（KV=6.18.60 / 7.2.8）→ `build-modules.sh`（厂商模块）→ 产物 `Image` + 2952 个 `.ko` + `kernel.config`。
`make-bundle.sh` 的审计会在我们的改动下失败，所以 bundle 在本地组装：

- `upstream/wrap-image.py` 处理 Image（LK 需要 0x180000 stub）
- `boot/build-boot-image.py --generic-ramdisk` 生成 ramdisk（init + busybox + 27 个启动模块）
- 加 `modules/`、`modules.builtin*`、`kernel.release`、`devices=f50 u30air`、`features`
- **`kernel.release` 必须 LF**（Windows 文本模式写出 CRLF 会让模块目录变成 `6.18.60\r`，modprobe 全部失败，WiFi 起不来）

## 上机

```
adb push mu300-kernel-6.18.tar.gz /mnt/mu300-disk/.mu300-update/
adb shell 'MU300_KERNEL_BUNDLE=... MU300_RELEASE=v2026.11.02.1 mu300-update boot'
adb shell reboot
```

验证：

```
ufshcd-sprd 22000000.ufs: ufs device reset!
ufshcd-sprd 22000000.ufs: ufs host reset!
scsi host0: ufshcd
uname -r           -> 6.18.60
/dev/sda           -> 存在，/dev/sda1.. 分区可见
mount              -> /dev/loop0 on /mnt/mu300-disk (915.4G)
wlan0              -> AP, SSID ZTE_91C321, 5GHz ch36
sipa_eth8          -> 10.43.28.197, 默认路由
LuCI               -> 200
```

## 回滚

- 上机前 boot_b 备份：`D:\zhang\学习\_router\boot_b-backup-5.4.img`（sha256 `e8afed27…`）
- 设备上：`mu300-update rollback-boot`
- Android 侧：adb root 直接 `dd` 回备份（boot_b 64 MiB）

## 7.2.8

同一补丁 dry-run 可应用到 7.2.8（hunk 偏移 -3 行）。云端构建 run `44892470626` 进行中；产物出来后按同一流程组装 `mu300-kernel-7.2.tar.gz` 并上机验证。

## 上游

issue #396 已评论：https://github.com/dikeckaan/mu300-linux/issues/396#issuecomment-7060987176
