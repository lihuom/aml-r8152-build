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

# ---------- RX buffer: gfp matrix probe ----------
# Our tree and the box kernel disagree on gfp bit assignments. Probe a matrix
# of candidate masks (order 0, no extra flags) and log which ones succeed.
if "r8152-dbg-gfp" not in src:
    src = src.replace(
        "\trx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);\n",
        "\t{\n"
        "\t\tstatic const unsigned int gfps[] = {\n"
        "\t\t\t0x00000CC0, 0x00400CC0, 0x00800CC0, 0x00C00CC0,\n"
        "\t\t\t0x02000CC0, 0x02400CC0, 0x02800CC0, 0x02C00CC0,\n"
        "\t\t\t0x00004CC0, 0x03000CC0, 0x02404CC0, 0x00C04CC0\n"
        "\t\t};\n"
        "\t\tint ti;\n"
        "\t\tfor (ti = 0; ti < 12; ti++) {\n"
        "\t\t\tstruct page *tpg = alloc_pages(gfps[ti], 0);\n"
        "\t\t\tpr_info(\"r8152-dbg-gfp: mask=0x%08x page=%p\\n\", gfps[ti], tpg);\n"
        "\t\t\tif (tpg) __free_pages(tpg, 0);\n"
        "\t\t}\n"
        "\t}\n"
        "\trx_agg->page = alloc_pages(0xC000C0 | __GFP_COMP | __GFP_NOWARN, order);\n", 1)
    print("gfp matrix:", "r8152-dbg-gfp" in src)
# Our 4.9.113 tree computes GFP_KERNEL as 0x24000C0, but this Amlogic kernel
# fails alloc_pages() with it even at order 0 (the same mask works for
# kmalloc because the slab path ignores the bogus bits).  The vanilla 4.9
# value 0xC000C0 is what the box kernel actually expects -- use it verbatim.
# NOTE: do NOT substitute kmalloc+virt_to_page here; skb_add_rx_frag takes a
# page ref and the release path ends in kfree() on a slab page -> Oops.
src = src.replace(
    "\trx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);\n",
    "\trx_agg->page = alloc_pages(0xC000C0 | __GFP_COMP | __GFP_NOWARN, order);\n", 1)

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

print("=== gfp.h bit definitions (OUR tree) ===")
import glob as _glob
for gh in _glob.glob("/tmp/linux-4.9.113/include/linux/gfp.h"):
    for ln in open(gh, encoding="utf-8", errors="replace").read().split("\n"):
        if ("___GFP_" in ln and "define" in ln) or "define GFP_KERNEL" in ln or "define __GFP_RECLAIM" in ln:
            print(ln.strip())

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)
print("kmalloc buffer :", "rx_agg->buffer = kmalloc" in src)
print("rx_buf_sz=4096 :", "tp->rx_buf_sz = 4096;" in src)
print("__free_pages left:", src.count("__free_pages("))
print("page_address left:", src.count("page_address("))
