# 电源感知性能配置（插电 / 电池双模式）

> 场景：U30 Air 既做插电路由器，也做随身 WiFi
> 目标：插电时性能拉满；电池时省电，但 USB 大流量仍能自动提速

## 1. 方案

```
power-profile.sh   每 15 秒读充电器状态
  在线 → 应用 performance 配置（三组 policy 全 performance）
  离线 → 应用 schedutil 配置（小核最低 614MHz）

usb0-gov.sh        读取 /run/power-profile.mode，动态提频
  AC  ：usb0 2 秒流量 >10MB(≈40Mbps) → performance，空闲 30 秒回落
  电池：usb0 2 秒流量 >30MB(≈120Mbps) → performance，空闲 15 秒回落
```

充电器状态取自：

```sh
/sys/class/power_supply/bq256xx-charger/online   # 1=插电
```

## 2. 为什么这样做

- 小核（A55）单包处理慢，USB 收包应交给大核（4-7）
- 但一直满频很费电（插电无所谓，电池不行）
- 所以：**空闲低功耗 + 大流量自动满频**，兼顾两者

## 3. 调速器选择依据（实测）

| 调速器 | 单流上行 | 说明 |
|---|---|---|
| schedutil | 2.6-2.8 Gbps | 动态；软中断负载不计入 PELT，可能不升频 |
| ondemand | 2.65 Gbps | 频率只到 1.1-1.3GHz，没拉满 |
| performance | 3.0-3.5 Gbps | 稳定满频，费电 |

> 单流波动较大（受 PC 端与温度影响）；4 流下 schedutil 与 performance 都在 5.3 Gbps 左右。

## 4. 系统已有接口

CPU 配置由固件自带的管理服务维护：

```sh
# 读取
echo '{}' | /usr/libexec/unisoc-modem/cpu get   # 实际上直接读 /etc/unisoc-modem/cpu.json
# 应用（stdin 传 JSON）
printf '%s' '{"scope":"frequency","persist":true,"changes":[...]}' | \
  /usr/libexec/unisoc-modem/cpu apply
```

持久化文件：`/etc/unisoc-modem/cpu.json`（version 2）。

> 注意：`apply` 的 payload 结构是 `{scope,persist,changes}`；
> 直接写 `{version,frequency}` 会返回 `CPU 配置无效`。

## 5. 部署文件

| 文件 | 作用 |
|---|---|
| `/usr/bin/power-profile.sh` | 电源模式切换 |
| `/usr/bin/usb0-gov.sh` | USB 流量自适应调速 |
| `/etc/init.d/power-profile` | 开机自启（START=98）|
| `/etc/init.d/usb0-gov` | 开机自启（START=99）|
| `/etc/hotplug.d/net/20-usb0-tune` | USB 上线时应用 RPS/中断/缓冲 |

脚本见仓库 `scripts/`。

## 6. 日志

```sh
logread | grep -E 'power-profile|usb0-gov'
# governor -> performance
# mode -> batt
```

## 7. 功耗参考

| 部件 | 典型功耗 |
|---|---|
| 4×A55 满载 | ~1-1.5W |
| 4×A76 满载 | 4-8W |
| 5G 基带驻网 | 2-4W |
| WiFi AP | 0.5-1W |

> 随身 WiFi 的耗电大头是 5G 基带，CPU 调优只能省 1-2W，但胜在零风险。
