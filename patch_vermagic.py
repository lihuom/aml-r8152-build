import struct

SRC = r"D:/tmp/rtl8153/r8152.ko"
DST = r"D:/tmp/rtl8153/r8152_patched.ko"
OLD = b"4.9.113 SMP preempt mod_unload modversions ARMv7 p2v8 "
NEW = b"4.9.y SMP preempt mod_unload modversions ARMv7 "

d = bytearray(open(SRC, "rb").read())

(e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
 e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = \
    struct.unpack_from("<HHIIIIIHHHHHH", d, 16)

shdrs = []
for i in range(e_shnum):
    o = e_shoff + i * e_shentsize
    shdrs.append(struct.unpack_from("<IIIIIIIIII", d, o))

shstr = shdrs[e_shstrndx]
shstr_data = bytes(d[shstr[4]:shstr[4] + shstr[5]])

def name_of(idx):
    n_off = shdrs[idx][0]
    end = shstr_data.find(b"\x00", n_off)
    return shstr_data[n_off:end].decode("latin1")

mi = None
for i in range(e_shnum):
    if name_of(i) == ".modinfo":
        mi = i
        break
if mi is None:
    raise SystemExit("no .modinfo")

off, size = shdrs[mi][4], shdrs[mi][5]
seg = bytes(d[off:off+size])
print("modinfo size:", size)

idx = seg.find(OLD)
if idx < 0:
    raise SystemExit("vermagic string not found in .modinfo")
print("found vermagic at .modinfo+0x%x" % idx)
print("old len:", len(OLD), "new len:", len(NEW))

# sanity: vermagic must be the last entry (only padding after it)
tail = seg[idx+len(OLD):]
print("bytes after vermagic:", len(tail), "all zero:", all(b == 0 for b in tail))

repl = NEW + b"\x00" * (len(OLD) - len(NEW))
d[off+idx: off+idx+len(OLD)] = repl

open(DST, "wb").write(bytes(d))
print("written:", DST)

# verify
chk = open(DST, "rb").read()
seg2 = chk[off:off+size]
i2 = seg2.find(b"vermagic=")
print("new entry:", seg2[i2:seg2.find(b"\x00", i2)].decode("latin1"))
