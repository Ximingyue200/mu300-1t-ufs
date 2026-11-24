#!/bin/sh
# 电源感知性能配置：充电 -> 性能模式；电池 -> 省电模式
MODE_FILE=/run/power-profile.mode
LOG_TAG=power-profile
json_ac='{"scope":"frequency","persist":true,"changes":[{"id":"policy0","cpus":"0 1 2 3","governor":"performance","min":614400,"max":2002000},{"id":"policy4","cpus":"4 5 6","governor":"performance","min":768000,"max":2301000},{"id":"policy7","cpus":"7","governor":"performance","min":1228800,"max":2210000}]}'
json_batt='{"scope":"frequency","persist":true,"changes":[{"id":"policy0","cpus":"0 1 2 3","governor":"schedutil","min":614400,"max":2002000},{"id":"policy4","cpus":"4 5 6","governor":"schedutil","min":768000,"max":2301000},{"id":"policy7","cpus":"7","governor":"schedutil","min":1228800,"max":2210000}]}'
cur=""
apply_mode() {
  [ "$cur" = "$1" ] && return
  case "$1" in
    ac)   printf '%s' "$json_ac"   | /usr/libexec/unisoc-modem/cpu apply >/dev/null 2>&1 ;;
    batt) printf '%s' "$json_batt" | /usr/libexec/unisoc-modem/cpu apply >/dev/null 2>&1 ;;
  esac
  cur="$1"; echo "$1" > "$MODE_FILE"
  logger -t $LOG_TAG "mode -> $1"
}
while true; do
  on=$(cat /sys/class/power_supply/bq256xx-charger/online 2>/dev/null || echo 1)
  if [ "$on" = "1" ]; then apply_mode ac; else apply_mode batt; fi
  sleep 15
done
