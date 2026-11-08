#!/usr/bin/env python3
"""Adapt Realtek official r8152 (v2.22.x) to linux-4.9 on this Amlogic box.

Box-specific findings:
 1. alloc_pages() always fails on this kernel -- even order 0, even though
    kmalloc() with the exact same gfp mask succeeds and the buddy allocator
    reports free blocks. So RX buffers are obtained via kmalloc() instead of
    alloc_pages() + page_address().
 2. 4.9 lacks skb_queue_len_lockless(); compat_ptr()/compat_ifreq are
    CONFIG_COMPAT-only and this is a 32-bit kernel.
"""
import re

P = "/tmp/linux-4.9.113/drivers/net/usb/r8152.c"
src = open(P, encoding="utf-8", errors="replace").read()
orig = src

# ---------- 4.9 API compat ----------
if "skb_queue_len_lockless" in src and "define skb_queue_len_lockless" not in src:
    add = "\n\n#ifndef skb_queue_len_lockless\n#define skb_queue_len_lockless(q) skb_queue_len(q)\n#endif"
    anchor = '#include "compatibility.h"'
    src = src.replace(anchor, anchor + add, 1) if anchor in src else add + "\n" + src
    print("patched: skb_queue_len_lockless")

if "compat_ptr" in src:
    if "#include <linux/compat.h>" not in src:
        anchor = '#include "compatibility.h"'
        src = src.replace(anchor, anchor + "\n#include <linux/compat.h>", 1) if anchor in src else "#include <linux/compat.h>\n" + src
    src = src.replace("struct compat_ifreq *ifr32 = (struct compat_ifreq *)ifr;", "")
    src = re.sub(r'compat_ptr\(ifr32->ifr_data\)', 'ifr->ifr_data', src)
    print("patched: compat branch")

# ---------- RX buffer: kmalloc instead of alloc_pages ----------
src = src.replace(
    "\trx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);\n",
    "\trx_agg->buffer = kmalloc(tp->rx_buf_sz, mflags);\n"
    "\trx_agg->page = rx_agg->buffer ? virt_to_page(rx_agg->buffer) : NULL;\n", 1)
src = src.replace("\trx_agg->buffer = page_address(rx_agg->page);\n", "", 1)
src = src.replace("\tif (!rx_agg->page)\n\t\tgoto free_rx;\n",
                  "\tif (!rx_agg->buffer)\n\t\tgoto free_rx;\n", 1)
src = src.replace("\t__free_pages(rx_agg->page, order);\n",
                  "\tkfree(rx_agg->buffer);\n", 1)
src = src.replace("\t__free_pages(agg->page, get_order(tp->rx_buf_sz));\n",
                  "\tkfree(agg->buffer);\n", 1)

# ---------- RX buffer size: 4K (fits a slab cache) ----------
src = src.replace(
    "\tnode = netdev->dev.parent ? dev_to_node(netdev->dev.parent) : -1;\n",
    "\tnode = netdev->dev.parent ? dev_to_node(netdev->dev.parent) : -1;\n"
    "\ttp->rx_buf_sz = 4096;\n", 1)

_re = re

# ---------- link-state instrumentation ----------
if "r8152-dbg-speed" not in src:
    src = src.replace(
        "\tspeed = rtl8152_get_speed(tp);\n",
        '\tspeed = rtl8152_get_speed(tp);\n'
        '\tpr_info("r8152-dbg-speed: raw=0x%04x link_bit=%d\\n",\n'
        '\t\tspeed, ((speed & LINK_STATUS) ? 1 : 0));\n', 1)
    print("speed instrumentation:", "r8152-dbg-speed" in src)

print("=== get_speed implementations ===")
for _m in re.finditer(r'\nstatic [^\n]*(get_speed|linked)\s*\(.*?\n\}\n', src, re.S):
    block = _m.group(0)
    if len(block) < 1200:
        for ln in block.split("\n"):
            print(ln)
        print("---")

print("=== PLA_PHYSTATUS refs ===")
for i, ln in enumerate(src.split("\n")):
    if "PLA_PHYSTATUS" in ln or "LINK_STATUS" in ln:
        print(f"{i+1}| {ln}")

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)
print("kmalloc buffer :", "rx_agg->buffer = kmalloc" in src)
print("rx_buf_sz=4096 :", "tp->rx_buf_sz = 4096;" in src)
print("__free_pages left:", src.count("__free_pages("))
print("page_address left:", src.count("page_address("))
