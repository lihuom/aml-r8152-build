#!/system/bin/sh
# Network stability watchdog - samples eth1 health every 10s.
# Survives in background; log persists in /data.
LOG=/data/stability.log
GW=192.168.6.1

echo "=== watchdog started $(date '+%m-%d %H:%M:%S') ===" >> $LOG

while true; do
    ts=$(date '+%m-%d %H:%M:%S')
    c=$(cat /sys/class/net/eth1/carrier 2>/dev/null || echo NA)
    s=$(cat /sys/class/net/eth1/speed 2>/dev/null || echo NA)
    rx=$(cat /sys/class/net/eth1/statistics/rx_packets 2>/dev/null || echo NA)
    tx=$(cat /sys/class/net/eth1/statistics/tx_packets 2>/dev/null || echo NA)
    rxe=$(cat /sys/class/net/eth1/statistics/rx_errors 2>/dev/null || echo NA)
    txe=$(cat /sys/class/net/eth1/statistics/tx_errors 2>/dev/null || echo NA)
    mf=$(awk '/MemFree/{print $2}' /proc/meminfo 2>/dev/null)
    # kernel oops counter so far
    up=$(cat /proc/uptime | awk '{print int($1)}')
    if [ "$c" = "1" ]; then
        ok=$(ping -I eth1 -c 1 -W 2 $GW > /dev/null 2>&1 && echo PASS || echo FAIL)
    else
        ok="DOWN"
    fi
    echo "$ts up=${up}s carrier=$c speed=$s rx=$rx tx=$tx rxerr=$rxe txerr=$txe gw=$ok memfree_kb=$mf" >> $LOG
    sleep 10
done
