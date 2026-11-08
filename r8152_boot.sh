#!/system/bin/sh
# Auto-configure the USB Ethernet adapter (r8152 / eth1) at boot.
LOG=/data/r8152_boot.log

log() { echo "$(date '+%m-%d %H:%M:%S') $1" >> $LOG; }

log "=== boot script start ==="

# wait up to 30s for the interface to appear
i=0
while [ $i -lt 30 ]; do
    [ -d /sys/class/net/eth1 ] && break
    i=$((i + 1))
    sleep 1
done

if [ ! -d /sys/class/net/eth1 ]; then
    log "ERROR: eth1 never appeared after ${i}s"
    exit 1
fi
log "eth1 present after ${i}s"

out=$(ip addr add 192.168.6.200/24 dev eth1 2>&1)
log "addr_add rc=$? out=[$out]"

out=$(ip link set eth1 up 2>&1)
log "link_up rc=$? out=[$out]"

log "=== done, addr now: $(ip -o addr show eth1 2>&1) ==="
exit 0
