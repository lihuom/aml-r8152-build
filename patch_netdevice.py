#!/usr/bin/env python3
"""Realign struct net_device with the Amlogic box kernel.

Offsets measured by disassembling the box vmlinux:
  netdev_ops @ 312   (standard linux-4.9.113: 304)  -> +8
  type       @ 348   (standard: 340)                -> +8
  addr_len   @ 391   (standard: 383)                -> +8
  dev_addrs  @ 432   (standard: 424)                -> +8
  dev_addr   @ 488   (standard: 480)                -> +8

All verified fields shifted by exactly +8, so the box adds one 8-byte
field (2 pointers) before netdev_ops. A single 8-byte pad there fixes
the whole struct.
"""
import re

P = "/tmp/linux-4.9.113/include/linux/netdevice.h"
src = open(P, encoding="utf-8", errors="replace").read()
orig = src

# +8 right before netdev_ops -> shifts netdev_ops/ethtool_ops/type/addr_len by 8
if "__aml_pad_head" not in src:
    src, n1 = re.subn(r'\n(\tconst struct net_device_ops \*)netdev_ops;',
                      r'\n\tu32 __aml_pad_head[2];\n\1netdev_ops;', src, count=1)
    print("pad +8 before netdev_ops:", n1)

# NOTE: no padding before dev_addr. Verified via eth_commit_mac_addr_change:
#   ldr r3, [r0, #0x1e8]   -> box dev_addr = 488 = standard 480 + 8
# The earlier "528" reading was dev->broadcast, not dev_addr.

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)
