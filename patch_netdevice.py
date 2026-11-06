#!/usr/bin/env python3
"""Realign struct net_device with the Amlogic box kernel.

Measured by disassembling the box vmlinux:
  type     @ 348  (standard linux-4.9.113: 340)  -> +8
  dev_addr @ 528  (standard linux-4.9.113: 480)  -> +48

So there are 8 extra bytes somewhere before `type`, and another 40 extra
bytes somewhere between `type` and `dev_addr`. Padding at these two anchors
shifts everything after them by the right amount.
"""
import re

P = "/tmp/linux-4.9.113/include/linux/netdevice.h"
src = open(P, encoding="utf-8", errors="replace").read()
orig = src

if "__aml_pad_type" not in src:
    src, n1 = re.subn(r'\n(\tunsigned short)(\s+)type;',
                      r'\n\tu32 __aml_pad_type[2];\n\1\2type;', src, count=1)
    print("pad +8 before 'type':", n1)

if "__aml_pad_devaddr" not in src:
    src, n2 = re.subn(r'\n(\tunsigned char)(\s+)\*dev_addr;',
                      r'\n\tu32 __aml_pad_devaddr[10];\n\1\2*dev_addr;', src, count=1)
    print("pad +40 before 'dev_addr':", n2)

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)
