#!/usr/bin/env python3
"""Realign struct net_device with the Amlogic box kernel.

Offsets measured by disassembling the box vmlinux:
  netdev_ops @ 312   (standard linux-4.9.113: 304)  -> +8  before netdev_ops
  addr_len   @ 391   (standard: 383)                -> +8  (consistent)
  type       @ 348   (standard: 340)                -> +8  (consistent)
  dev_addr   @ 528   (standard: 480)                -> +48 total

So: +8 bytes somewhere before netdev_ops, and another +40 between
type/addr_len and dev_addr.
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

# +40 right before dev_addr -> shifts dev_addr and everything after by 40
if "__aml_pad_devaddr" not in src:
    src, n2 = re.subn(r'\n(\tunsigned char)(\s+)\*dev_addr;',
                      r'\n\tu32 __aml_pad_devaddr[10];\n\1\2*dev_addr;', src, count=1)
    print("pad +40 before dev_addr:", n2)

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)
