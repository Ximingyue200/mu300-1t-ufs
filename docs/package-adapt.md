# k7.2.8 桌面包 · 1TB UFS 适配记录

产物：`D:\zhang\学习\_router\mu300-openwrt-25.12.5-r20261120.124754-g1ebe6dd0-s11b3fb6b-k7.2.8-ufs7.zip`（187 MB）
验证：在 1TB UFS 设备上完整安装并启动成功（2026-11-21 19:4x）

## 装完后的设备状态

```
kernel  7.2.8（主线 + UFS 补丁）
系统    mu300-r20261120.124754-g1ebe6dd0-s11b3fb6b（OpenWrt 25.12.5）
UFS     /dev/sda 枚举正常，根 /dev/loop0 915.4G
WiFi    wlan0 AP，SSID ZTE_91C321，5GHz ch36（自动启动）
数据    sipa_eth8 10.82.2.82，默认路由（SIM2）
LuCI    http://192.168.77.1/  → 200
密码    root / root1234
回滚    /mnt/mu300-disk/openwrt-luci.old（上一版系统）
```

## 四处适配

1. **启动镜像**
   `payload/boot-linux.img` → 换成设备上验证过的 7.2.8+UFS 镜像（sha `047054a3…`，header v4、AVK footer、wrap stub、`sprd,ufshc` 都在）。

2. **rootfs 内核模块**
   `lib/modules/7.2.8` 原来是发行者构建的 206 个模块，与我们的内核 `struct module` 尺寸不匹配
   （vermagic 相同但配置不同，`modprobe` 报 `.gnu.linkonce.this_module section size must match`），
   换成我们构建的 **3039 个模块**；`rootfs.requirements` 相应更新为 `800000 40000`。

3. **`desktop/update_control.py`**
   - 设备是“最后分区之后的 raw 区域 + loop”的布局，原来被误判成 `legacy`（eMMC 隐藏区）→ 探测失败；
     现在 `/dev/loop*`、`/dev/sd*` 判定为 `part`
   - 该布局下**直接使用包内启动镜像**，不让 `boot_image.build()` 重建
     （重建会写入 `part` 模式的 storage 脚本，init 找不到区域 loop，实测起不来）
   - info 探测多读一行 `disk-dev` 用于判断

4. **`desktop/mu300-update-library.sh` + `desktop/local-update.sh`**
   支持 `openwrt-luci` 这个系统名（设备实际目录名）：
   `running_os`、`installed_systems`、`mounted_disk`、`keep_list`、`vendor_list`、apply 白名单，
   以及 `local-update.sh` 里所有 `$DISK/openwrt` 路径、`apply_one`、`boot-os` 写入。

## 用这个包装机

1. 设备进 Linux（本机 adb 也可），确保 SSH `root` 可登录
2. 完整解压 zip，双击 `OpenWrt-Installer.exe` → “更新 OpenWrt”，地址填设备 IP（现在是 `192.168.77.1`）、密码 `root1234`
3. 或者用命令行（cli 入口有相对导入 bug，用驱动脚本）：
   `python run_update7f.py <设备IP>`

更新会保留 `/etc/config` 等设置、保留旧系统为 `openwrt-luci.old`，完成后自动重启。

## 注意

- 装完 LAN 会变成 **192.168.77.1**（包内默认；之前是 192.168.78.1）
- 内核必须保持 7.2.8（或 6.18/7.2 系列，且带 UFS 补丁）；**不要切到没有 UFS 驱动的构建**
- 不要再用原始 k7.2.8 包装机：它的内核没有 UFS 驱动、模块与我们的内核不匹配
