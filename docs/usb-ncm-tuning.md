# USB NCM 网络共享性能调优（U30 Air / UFS 版）

> 场景：U30 Air 通过 USB-C 以 NCM 方式把 5G 网络共享给电脑
> 目标：把 USB 链路从 ~585 Mbps 拉到接近 USB3 实际上限
> 结论：**决定因素是「收包中断 + RPS 绑大核」和「关闭 RFS」**，与线材无关

## 1. 硬件与初始状态

```
主机：USB-C（USB3，链路协商 4.2 Gbps）
设备：U30 Air，T760/UMS9620，4×A55(0-3) + 4×A76(4-7)
gadget：acm.GS0（串口）+ ncm.usb0（网络），usb0 桥进 br-lan
系统：OpenWrt 25.12.5 + mainline 7.3.1
```

初始 iperf3（TCP，PC→U30）：**约 585 Mbps**（U30→PC 约 1.75 Gbps）。

## 2. 定位过程

### 2.1 排除物理层

- UDP 测试出现 30-70% 丢包，但 `usb0` 统计 `rx_errors/fifo/frame = 0`，jitter 极低
- 换短的高规格线无改善 → 不是线材/PHY

### 2.2 计数对照

```
usb0 rx_packets 增量 ≈ UDP InDatagrams 增量 → 包确实进了网卡
但 sender 发出的包更多 → 丢在更前面（USB 传输/驱动层）
```

### 2.3 关键发现：中断和 RPS 全在小核

```
/proc/interrupts：dwc3 中断 100% 落在 cpu0（A55 小核）
/sys/class/net/usb0/queues/rx-0/rps_cpus = 01（只允许 cpu0）
```

把 RPS 改到 `ff`（八核）后 TCP 上行升到 3.35 Gbps，但**UDP 反而更差**；
进一步观察发现：小核单包处理慢，且应用线程被调度到小核时整体被拖慢。

## 3. 最终配置（最优）

```sh
# 1) RPS 只给大核（bitmap 0xf0 = cpu4-7）
for q in /sys/class/net/usb0/queues/rx-*/rps_cpus; do echo f0 > "$q"; done

# 2) 关闭 RFS（rps_flow_cnt=0），否则会按应用线程所在 CPU 把包拉回小核
for q in /sys/class/net/usb0/queues/rx-*/rps_flow_cnt; do echo 0 > "$q"; done
echo 0 > /proc/sys/net/core/rps_sock_flow_entries

# 3) dwc3 中断绑大核
irq=$(awk '/dwc3/ {gsub(":","",$1); print $1; exit}' /proc/interrupts)
echo 4-7 > /proc/irq/$irq/smp_affinity_list

# 4) 缓冲
echo 65536 > /proc/sys/net/core/netdev_max_backlog
echo 16777216 > /proc/sys/net/core/rmem_max
echo 8388608  > /proc/sys/net/core/rmem_default
echo 16777216 > /proc/sys/net/core/wmem_max
```

开机自动生效：`/etc/hotplug.d/net/20-usb0-tune`（见 `scripts/usb0-tune`）。

## 4. 实测结果

| 配置 | TCP 上行单流 | TCP 上行 4 流 | TCP 下行 |
|---|---|---|---|
| 默认（RPS=cpu0） | 585 Mbps | 605 Mbps | 1.75 Gbps |
| RPS=ff（八核） | 1.16 Gbps | 2.71 Gbps | — |
| **RPS=f0 + IRQ 4-7 + 关 RFS** | **4.0-4.5 Gbps** | **5.3-5.4 Gbps** | ~1.9 Gbps |

> 4 流上行 5.3 Gbps 已接近 USB3.0 实际可用上限（存储实测 3.2-3.6 Gbps，NCM 略有不同）。
> 下行约 1.9 Gbps 与 CPU 无关（关小核/锁频都不变），受 U30 发包路径或 Windows NCM 驱动限制。

## 5. 踩坑记录

| 现象 | 原因 |
|---|---|
| RPS=ff 反而更慢 | 小核处理 USB 收包效率低，跨核分发有开销 |
| 设了 RPS 但速度回落到 1 Gbps | 同时设置了 `rps_flow_cnt` → 启用 RFS，把流绑回应用线程所在小核 |
| "小核满载"时上行掉 30% | 应用线程被调度到小核，与负载争抢 CPU |
| UDP 大量丢包 | 正常：iperf UDP 逐包处理，NCM/内核无 GRO 聚合；TCP 有聚合所以快得多 |

## 6. 验证命令

```sh
cat /sys/class/net/usb0/queues/rx-0/rps_cpus           # 期望 f0
cat /proc/irq/$(awk '/dwc3/{gsub(":","",$1);print $1;exit}' /proc/interrupts)/smp_affinity_list  # 期望 4-7
cat /sys/class/net/usb0/queues/rx-0/rps_flow_cnt       # 期望 0

# 本机测速（需 iperf3）
iperf3 -c <对端> -t 8
iperf3 -c <对端> -t 8 -P 4
```
