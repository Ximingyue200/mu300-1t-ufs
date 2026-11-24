# UFS 存储实测（三星 KLUGGARHGB-B0E1 1TB）

> 设备：ZTE U30 Air 1TB（UFS 3.1，三星 KLUGGARHGB-B0E1）
> 系统：OpenWrt 25.12.5 + mainline 7.3.1 + `0022-ufs-sprd-accept-the-firmware-dt.patch`
> 目的：验证 UFS 补丁是否真正可用、速度是否正常

## 1. 容量

```sh
blockdev --getsize64 /dev/sda            # 1,023,678,611,456 字节 = 953 GiB
cat /sys/block/sda/size                  # 1,999,372,288 扇区 (512B)
```

根文件系统所在：`/dev/loop0`（ext4，镜像在 /dev/sda 上），挂载 `/mnt/mu300-disk`，可用 915.4 GiB。

## 2. 裸盘（/dev/sda，绕开 loop）

| 测试 | 结果 |
|---|---|
| 128K 顺序读 QD32 | **1.17 GB/s**（fio: 1,227,599 KB/s）|
| 4K 随机读 QD32 | **155 MB/s / 39,693 IOPS** |

## 3. 文件系统（ext4 on loop）

| 测试 | 结果 |
|---|---|
| 顺序写（dd O_DIRECT 4G） | ~1.0 GB/s |
| 顺序读（dd O_DIRECT 4G） | ~1.37 GB/s（loop 缓存有虚高，裸盘 1.17GB/s 为准）|
| 4K 随机读 QD32 | 155 MB/s / 39.6k IOPS |
| 4K 随机写 QD32 | 149 MB/s / 38k IOPS |
| 128K 顺序写 QD32 | ~1.41 GB/s |

## 4. 与 eMMC 版本对比（量级）

| 项 | eMMC 版 | 本机 UFS |
|---|---|---|
| 顺序读 | ~300 MB/s | **~1,170 MB/s** |
| 随机读 | ~30-50 MB/s | **~155 MB/s** |

## 5. 结论

- 补丁让 1TB UFS 真正可用，顺序速度接近颗粒上限
- 随机 39k IOPS 偏低：mainline `ufs-sprd` 驱动未做队列/调度优化（非补丁问题）
- 日常 NAS/下载/服务场景完全够用

## 6. 复现命令

```sh
apk add fio
# 裸盘顺序读
fio --filename=/dev/sda --size=512M --ioengine=libaio --direct=1 \
    --time_based --runtime=10 --name=rawsr --bs=128k --iodepth=32 --rw=read
# 裸盘随机读
fio --filename=/dev/sda --size=1G --ioengine=libaio --direct=1 \
    --time_based --runtime=10 --name=rawrr --bs=4k --iodepth=32 --rw=randread
# 文件系统随机写
fio --filename=/mnt/mu300-disk/fiotest --size=2G --ioengine=libaio --direct=1 \
    --time_based --runtime=15 --name=rw --bs=4k --iodepth=32 --rw=randwrite
```
