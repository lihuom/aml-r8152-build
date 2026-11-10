#!/system/bin/sh
# Network watchdog v2 - runs from boot (init service), samples eth1 every 10s.
# On first failure it captures dmesg evidence automatically.
# Log rotates at ~2MB (stability.log -> stability.log.1).
LOG=/data/stability.log
GW=${GW:-192.168.6.1}
MAXSIZE=2000000

log() { echo "$1" >> $LOG; }
rotate() {
    sz=$(ls -l $LOG 2>/dev/null | awk '{print $5}')
    [ -n "$sz" ] && [ "$sz" -gt "$MAXSIZE" ] && mv $LOG $LOG.1
}

log "=== watchdog v2 started $(date '+%m-%d %H:%M:%S') ==="
fail_streak=0

while true; do
    rotate
    ts=$(date '+%m-%d %H:%M:%S')
    c=$(cat /sys/class/net/eth1/carrier 2>/dev/null || echo NA)
    s=$(cat /sys/class/net/eth1/speed 2>/dev/null || echo NA)
    ipaddr=$(ip -o addr show eth1 2>/dev/null | awk '{print $4}' | head -1)
    rx=$(cat /sys/class/net/eth1/statistics/rx_packets 2>/dev/null || echo NA)
    tx=$(cat /sys/class/net/eth1/statistics/tx_packets 2>/dev/null || echo NA)
    rxe=$(cat /sys/class/net/eth1/statistics/rx_errors 2>/dev/null || echo NA)
    mf=$(awk '/MemFree/{print $2}' /proc/meminfo 2>/dev/null)
    up=$(awk '{print int($1)}' /proc/uptime)
    if [ "$c" = "1" ]; then
        ok=$(ping -I eth1 -c 1 -W 2 $GW > /dev/null 2>&1 && echo PASS || echo FAIL)
    else
        ok=DOWN
    fi
    log "$ts up=${up}s carrier=$c speed=$s ip=$ipaddr rx=$rx tx=$tx rxerr=$rxe gw=$ok memfree_kb=$mf"

    if [ "$ok" != "PASS" ]; then
        fail_streak=$((fail_streak + 1))
        if [ "$fail_streak" = "1" ]; then
            log "  !!! FIRST FAILURE at $ts — capturing evidence"
            dmesg | tail -50 | grep -viE "vdec|is_reset" >> $LOG
            log "  devnum=$(cat /sys/bus/usb/devices/1-2/devnum 2>/dev/null)"
        fi
    else
        fail_streak=0
    fi
    sleep 10
done
