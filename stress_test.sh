#!/system/bin/sh
# Stress test: repeatedly pull 100MB over eth1 from 192.168.6.154,
# log per-round throughput. 30 rounds ~= 1 hour at ~200Mbps.
LOG=/data/stress.log
URL=http://192.168.6.154:9000/test100m.bin
OUT=/data/stress.bin
ROUNDS=30

echo "=== stress started $(date '+%m-%d %H:%M:%S') ===" >> $LOG

i=1
while [ $i -le $ROUNDS ]; do
    start=$(date +%s)
    busybox wget -q -T 120 -O $OUT $URL 2>/dev/null
    rc=$?
    end=$(date +%s)
    ms=$(( (end - start) * 1000 / 1 ))
    sec=$((end - start))
    bytes=$(ls -l $OUT 2>/dev/null | awk '{print $5}')
    if [ "$rc" = "0" ] && [ "$sec" -gt 0 ]; then
        mbps=$(busybox awk "BEGIN{printf \"%.0f\", 8*104857600/1000000/$sec}")
        mbps5=$(busybox awk "BEGIN{printf \"%.1f\", 104857600/1048576/$sec}")
        echo "round $i rc=0 ${sec}s bytes=$bytes ${mbps}Mbps (${mbps5}MB/s)" >> $LOG
    else
        echo "round $i FAILED rc=$rc after ${sec}s bytes=$bytes" >> $LOG
    fi
    # verify content is not corrupted mid-way (size check)
    if [ "$bytes" != "104857600" ]; then
        echo "round $i SIZE MISMATCH ($bytes)" >> $LOG
    fi
    i=$((i + 1))
    sleep 2
done
echo "=== stress finished $(date '+%m-%d %H:%M:%S') ===" >> $LOG
