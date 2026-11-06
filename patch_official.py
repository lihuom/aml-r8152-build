#!/usr/bin/env python3
"""Adapt Realtek official r8152 (v2.22.x) to linux-4.9 headers."""
import re

P = "/tmp/linux-4.9.113/drivers/net/usb/r8152.c"
src = open(P, encoding="utf-8", errors="replace").read()
orig = src

# 1) skb_queue_len_lockless() appeared in 4.19
if "skb_queue_len_lockless" in src and "define skb_queue_len_lockless" not in src:
    anchor = '#include "compatibility.h"'
    if anchor in src:
        src = src.replace(anchor, anchor + """

#ifndef skb_queue_len_lockless
#define skb_queue_len_lockless(q) skb_queue_len(q)
#endif""", 1)
        print("patched: skb_queue_len_lockless via compatibility.h anchor")
    else:
        src = """#ifndef skb_queue_len_lockless
#define skb_queue_len_lockless(q) skb_queue_len(q)
#endif
""" + src
        print("patched: skb_queue_len_lockless via file head")

# 2) compat ioctl path: 4.9 32-bit ARM lacks those helpers in scope
if "compat_ptr" in src:
    if "#include <linux/compat.h>" not in src:
        anchor = '#include "compatibility.h"'
        if anchor in src:
            src = src.replace(anchor, anchor + "\n#include <linux/compat.h>", 1)
        else:
            src = "#include <linux/compat.h>\n" + src
        print("patched: added <linux/compat.h>")

# 3) compat ioctl branch: dead code on 32-bit kernels (in_compat_syscall() always false),
#    but still needs to compile -- it references CONFIG_COMPAT-only symbols.
if "compat_ptr" in src or "compat_ifreq" in src:
    src = src.replace("struct compat_ifreq *ifr32 = (struct compat_ifreq *)ifr;", "")
    src = re.sub(r'compat_ptr\(ifr32->ifr_data\)', 'ifr->ifr_data', src)
    print("patched: compat branch folded to 32-bit path")

# instrument alloc_all_mem + shrink rx buffer (order-3 32KB fails on this box)
if "r8152-dbg-sizes" not in src:
    src = src.replace(
        """	node = netdev->dev.parent ? dev_to_node(netdev->dev.parent) : -1;
""",
        """	node = netdev->dev.parent ? dev_to_node(netdev->dev.parent) : -1;
	tp->rx_buf_sz = 16384;
	pr_info("r8152-dbg-sizes: rx_buf_sz=%u node=%d mtu=%u order=%u\\n",
		tp->rx_buf_sz, node, netdev->mtu, get_order(tp->rx_buf_sz));
""", 1)
    print("instrumented alloc_all_mem:", "r8152-dbg-sizes" in src)

# trace the three allocations inside alloc_rx_agg
src = src.replace(
    """	rx_agg = kmalloc_node(sizeof(*rx_agg), mflags, node);
	if (!rx_agg)
		return NULL;
""",
    """	rx_agg = kmalloc_node(sizeof(*rx_agg), mflags, node);
	pr_info("r8152-dbg-agg: kmalloc=%p size=%u node=%d\\n",
		rx_agg, (unsigned)sizeof(*rx_agg), node);
	if (!rx_agg)
		return NULL;
""", 1)

src = src.replace(
    """	rx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);
	if (!rx_agg->page)
		goto free_rx;
""",
    """	rx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);
	pr_info("r8152-dbg-agg: page=%p order=%u mflags=0x%x\\n",
		rx_agg->page, order, mflags);
	if (!rx_agg->page)
		goto free_rx;
""", 1)

src = src.replace(
    """	rx_agg->urb = usb_alloc_urb(0, mflags);
	if (!rx_agg->urb)
		goto free_buf;
""",
    """	rx_agg->urb = usb_alloc_urb(0, mflags);
	pr_info("r8152-dbg-agg: urb=%p\\n", rx_agg->urb);
	if (!rx_agg->urb)
		goto free_buf;
""", 1)

# TEST: drop __GFP_COMP/__GFP_NOWARN to see if the flag bits are the problem
src = src.replace(
    """	rx_agg->page = alloc_pages(mflags | __GFP_COMP | __GFP_NOWARN, order);""",
    """	rx_agg->page = alloc_pages(mflags, order);""", 1)
print("flags test applied:", "alloc_pages(mflags, order)" in src)

# dump gfp-related defines from compatibility.h
import glob
for cf in glob.glob("/tmp/realtek-r8152-linux-*/compatibility.h"):
    print(f"=== __GFP defines in {cf} ===")
    for ln in open(cf, encoding="utf-8", errors="replace").read().split("\n"):
        if "__GFP" in ln:
            print(ln)

lines = src.split("\n")
print("=== alloc_rx_agg definition ===")
started = False
for i, ln in enumerate(lines):
    if "static struct rx_agg *alloc_rx_agg" in ln:
        started = True
    if started:
        print(f"{i+1}| {ln}")
        if ln.startswith("}") and i > 0:
            break

# report what remains
for tok in ("skb_queue_len_lockless", "compat_ptr", "compat_ifreq"):
    hits = [i + 1 for i, ln in enumerate(lines) if tok in ln]
    print(f"REMAINING {tok}: {hits[:8]}")

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig)

m = re.search(r'\nstatic int __rtl8152_set_mac_address\(.*?\n\}\n', src, re.S)
if m:
    print("=== __rtl8152_set_mac_address ===")
    for ln in m.group(0).split("\n")[:55]:
        print(ln)
