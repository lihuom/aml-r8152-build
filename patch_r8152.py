#!/usr/bin/env python3
"""Adapt linux-4.19 r8152.c to build against linux-4.9 headers.

Removes APIs that did not exist in 4.9:
  - net_device.min_mtu / max_mtu   (added in 4.10)
  - ETH_MIN_MTU                    (added in 4.10)
  - ethtool get/set_link_ksettings (added in 4.19)
  - mii_ethtool_get_link_ksettings (added in 4.17)
"""
import re
import sys

P = "/tmp/linux-4.9.113/drivers/net/usb/r8152.c"
src = open(P, encoding="utf-8", errors="replace").read()
orig = src


def drop_func(s, name):
    """Remove a top-level C function definition by name (brace matched)."""
    pat = re.compile(r'\n(static\s+[^\n;{]*?\b' + re.escape(name) + r'\s*\([^;{]*?\)\s*)\{')
    m = pat.search(s)
    if not m:
        return s, False
    i = m.end()
    depth = 1
    while i < len(s) and depth:
        c = s[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    while i < len(s) and s[i] in '\r\n':
        i += 1
    return s[:m.start()] + '\n' + s[i:], True


# 1) ETH_MIN_MTU was introduced in 4.10
if 'ETH_MIN_MTU' in src:
    src = "#ifndef ETH_MIN_MTU\n#define ETH_MIN_MTU 68\n#endif\n" + src
    print("patched: ETH_MIN_MTU defined")

# 2) net_device.min_mtu / max_mtu do not exist in 4.9
before = src
src = re.sub(r'[ \t]*netdev->min_mtu[ \t]*=[^;]*;\n', '', src)
src = re.sub(r'[ \t]*netdev->max_mtu[ \t]*=[^;]*;\n', '', src)
print("patched: min_mtu/max_mtu lines removed:", before != src)

# 3) ethtool link_ksettings API is 4.19+, drop those callbacks entirely
for fn in ("rtl8152_get_link_ksettings", "rtl8152_set_link_ksettings", "rtl8152_nway_reset"):
    src, ok = drop_func(src, fn)
    print(f"drop function {fn}: {ok}")

for key in (".get_link_ksettings", ".set_link_ksettings", ".nway_reset"):
    src = re.sub(r'\n[ \t]*' + re.escape(key) + r'[ \t]*=[^,\n]*,', '', src)

# 5) napi_complete_done() returns void in 4.9 (bool only from 4.11)
src2 = re.sub(r'if\s*\(\s*!napi_complete_done\(([^)]*)\)\s*\)[ \t]*\n[ \t]*goto\s+out;',
              'napi_complete(napi);', src)
if src2 != src:
    print("patched: napi_complete_done -> napi_complete")
src = src2

# 4) report remaining references so the build log is actionable
for token in ("mii_ethtool_get_link_ksettings", "min_mtu", "max_mtu", "link_ksettings",
              "napi_complete_done", "netif_napi_del"):
    hits = [i + 1 for i, ln in enumerate(src.split("\n")) if token in ln]
    if hits:
        print(f"REMAINING {token}: lines {hits[:10]}")

open(P, "w", encoding="utf-8", newline="\n").write(src)
print("changed:", src != orig, "size:", len(src))

# dump the region the compiler still complains about
lines = src.split("\n")
print("=== context 2040-2070 ===")
for i in range(2039, 2070):
    if i < len(lines):
        print(f"{i+1}| {lines[i]}")
