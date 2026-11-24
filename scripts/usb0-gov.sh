#!/bin/sh
# usb0 自适应调频（电源感知）
POL="4 7"
MODE_FILE=/run/power-profile.mode
idle=0; cur=""
setgov() {
  [ "$cur" = "$1" ] && return
  for p in $POL; do echo "$1" > /sys/devices/system/cpu/cpufreq/policy$p/scaling_governor 2>/dev/null; done
  cur="$1"; logger -t usb0-gov "governor -> $1"
}
while true; do
  mode=$(cat $MODE_FILE 2>/dev/null || echo batt)
  if [ "$mode" = "ac" ]; then TH=$((10*1024*1024)); IDLE_MAX=30
  else                        TH=$((30*1024*1024)); IDLE_MAX=15; fi
  r1=$(cat /sys/class/net/usb0/statistics/rx_bytes 2>/dev/null || echo 0)
  sleep 2
  r2=$(cat /sys/class/net/usb0/statistics/rx_bytes 2>/dev/null || echo 0)
  d=$((r2 - r1))
  if [ "$d" -gt "$TH" ]; then setgov performance; idle=0
  else idle=$((idle + 2)); [ "$idle" -ge "$IDLE_MAX" ] && setgov schedutil; fi
done
