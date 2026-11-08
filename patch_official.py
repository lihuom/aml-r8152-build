#!/usr/bin/env python3
"""Adapt Realtek official r8152 (v2.22.x) to linux-4.9 on this Amlogic box.

Box-specific findings:
 1. The box kernel's pglist_data layout DIFFERS from vanilla 4.9.113
    (live probe: node_zonelists is at offset 28 there, our tree computes
    2688).  Any alloc_pages() done from module code builds the zonelist
    pointer with OUR compile-time offset and therefore always fails,
    regardless of gfp mask.  Fix: allocate through get_zeroed_page(), an
    EXPORTED helper whose implementation lives inside the box vmlinux and
    uses the box's own layout.  Convert the returned linear address with
    virt_to_page() (FLATMEM, reliable) for skb_add_rx_frag().
 2. 4.9 lacks skb_queue_len_lockless(); compat_ptr()/compat_ifreq are
    CONFIG_COMPAT-only on this 32-bit kernel.
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

# ---------- RX buffer via get_zeroed_page (box-layout-safe) ----------
src = src.replace(
    "\trx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);\n",
    "\t{\n"
    "\t\tunsigned long va = get_zeroed_page(mflags);\n"
    "\t\trx_agg->page = va ? virt_to_page(va) : NULL;\n"
    "\t\trx_agg->buffer = (void *)va;\n"
    "\t\tpr_info(\"r8152-dbg-alloc: va=%08lx page=%p\\n\", va, rx_agg->page);\n"
    "\t}\n", 1)
src = src.replace("\trx_agg->buffer = page_address(rx_agg->page);\n", "", 1)
src = src.replace("\tif (!rx_agg->page)\n\t\tgoto free_rx;\n",
                  "\tif (!rx_agg->buffer)\n\t\tgoto free_rx;\n", 1)
src = src.replace("\t__free_pages(rx_agg->page, order);\n",
                  "\tfree_page((unsigned long)rx_agg->buffer);\n", 1)
src = src.replace("\t__free_pages(agg->page, get_order(tp->rx_buf_sz));\n",
                  "\tfree_page((unsigned long)agg->buffer);\n", 1)

# ---------- RX buffer size: 4K (get_zeroed_page is order-0 only) ----------
src = src.replace(
    "\tnode = netdev->dev.parent ? dev_to_node(netdev->dev.parent) : -1;\n",
    "\tnode = netdev->dev.parent ? dev_to_node(netdev->dev.parent) : -1;\n"
    "\ttp->rx_buf_sz = 4096;\n", 1)

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)
print("zeroed_page  :", "get_zeroed_page(mflags)" in src)
print("free_page    :", src.count("free_page(("))
print("alloc_pages left:", src.count("alloc_pages("))
print("rx_buf_sz=4096 :", "tp->rx_buf_sz = 4096;" in src)
