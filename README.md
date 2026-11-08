# aml-r8152-build

**Realtek RTL8153B USB-Gigabit Ethernet driver (official v2.22.1) ported to the Amlogic S905L3A Android 9 TV box (MECOOL KM9 Pro, kernel 4.9.113, armv7).**

为 MECOOL KM9 Pro 电视盒（Amlogic S905L3A，Android 9，内核 4.9.113 armv7）交叉编译 Realtek 官方 r8152 驱动（v2.22.1），驱动 RTL8153B（`0bda:8153`）USB 千兆网卡，并解决该魔改内核与主线 4.9 之间所有"看不见的差异"。

GitHub Actions 一键构建，产物 `out/r8152.ko` 已完成 vermagic 改写与 strip，可直接 insmod。

---

## 验证结果（2026-11-08）

| 项目 | 结果 |
|---|---|
| 链路协商 | 1000Mbps / Full duplex |
| Android 联网 | DHCP 自动获取 IP/路由/DNS，外网可达 |
| 压力测试 | 30 轮 × 100MB = **3GB，30/30 成功，零 SIZE MISMATCH** |
| 峰值吞吐 | **280Mbps（33.3MB/s）** —— USB 2.0 理论有效上限 |
| RX/TX 错误 | 全程 **0** |
| 内核崩溃 | **0**（多次插拔、重载、高负载视频播放环境下） |
| 内存 | MemFree 稳定，无泄漏 |

> 280Mbps 正好顶在 USB 2.0 的物理天花板上（480Mbps 理论 × 协议编码效率）。要跑满千兆请插 USB 3.0 口。

## 为什么需要这个仓库

盒子固件的内核：

- **没有编译 r8152**（`# CONFIG_USB_RTL8152 is not set`）；
- `CONFIG_MODVERSIONS=y` 且未开 `CONFIG_MODULE_FORCE_LOAD`，外部模块必须满足 vermagic 一致 + 所有符号 CRC 一致；
- **是 Amlogic 深度魔改的 4.9.113** —— 与主线 4.9.113 在若干数据结构布局上不兼容（见下文），这是整个移植里最隐蔽的部分。

## 四个坑与修复（核心章节）

### 1. modversions：10124 个符号 CRC

主线 4.9.113 源码编出的 `Module.symvers` CRC 全对不上（版本号就不同）。解法：
解析盒子 boot 分区里的 zImage → 解出 gzip 载荷得到 24.4MB 原始内核镜像 → 以
`_text = 0xc0108000` 建立虚拟地址→文件偏移映射 → 逐个 `__kcrctab_<sym>` 读出真实 CRC
（10124 项），并用 `__kstrtab_*` 反查符号名自校验。产物即本仓库的 `Module.symvers`。

### 2. vermagic：`4.9.113` vs `4.9.y`

盒子的内核版本串是 `4.9.y`（厂商把 SUBLEVEL 做成了占位符），模块必须逐字一致。
`patch_vermagic.py` 在 ELF 的 `.modinfo` 段就地改写 vermagic 字符串，长度差用零填充。

### 3. `struct net_device` 布局：整体 +8 字节

模块内 `dev->dev_addr` 一写就 NULL 指针崩溃。通过反汇编盒子 vmlinux 的四个函数交叉定位：

| 字段 | 主线 4.9.113 | 盒子 | 定位依据 |
|---|---|---|---|
| netdev_ops | 304 | **312** | `__dev_open` 首条 `ldr r6,[r0,#0x138]` |
| type | 340 | **348** | `ether_setup` `strh r4,[lr]`, lr=r0+348 |
| addr_len | 383 | **391** | `ether_setup` `strb r4,[r0,#0x187]` |
| dev_addrs | 424 | **432** | `dev_addr_add` `add r0,r4,#432` |
| dev_addr | 480 | **488** | `eth_commit_mac_addr_change` `ldr r3,[r0,#0x1e8]` |
| broadcast | 520 | 528 | `ether_setup` `mvn r2,#0` + `str r2,[r0,#0x210]` |

所有字段统一 +8 → 盒子在 `netdev_ops` 之前多了 8 字节字段。`patch_netdevice.py` 在
`include/linux/netdevice.h` 的 `netdev_ops` 声明前插入 `u32 __aml_pad_head[2];`，一处填充全体对齐。

### 4. `pglist_data` 布局被改 → 模块内 `alloc_pages()` 必败

修复完布局后 `up` 报 `ENOMEM`。排查路径：

- `/proc/pagetypeinfo` 显示 Normal/Unmovable 有大量空闲块（排除内存不足）；
- 12 种 gfp 掩码矩阵测试**全部失败**（排除 gfp 位定义差异）；
- 同掩码的 `kmalloc()` 成功（slab 路径不经过 pglist_data）；
- **模块内活体探针**扫描 `contig_page_data`：盒子的 `node_zonelists` 在 **pg_data+28**，
  而我们的编译树算出 **+2688**（`sizeof(zone)`=896 × MAX_NR_ZONES=3）——
  Amlogic 大改了 `pglist_data`/`struct zone` 布局。模块内任何 `alloc_pages()` 都用
  我们编译期偏移去取 zonelist → 读到垃圾 → 全部失败。

**修复**：RX 缓冲改用 `get_zeroed_page()` —— 内核**导出的真函数**，实现在 vmlinux 内部、
用盒子自己的布局，天然正确；返回的线性地址经 `virt_to_page()`（FLATMEM，可靠）转成 page
交给 `skb_add_rx_frag()`。释放用 `free_page()` 宏。

> ⚠️ 反面教材：不要用 `kmalloc() + virt_to_page()` 伪造 page。`skb_add_rx_frag()` 会取
> page 引用，skb 释放路径最终对 slab 页执行 `kfree()` → `Unable to handle kernel paging
> request ... PC is at kfree` 连环 Oops。**页的生命周期必须由页分配器管理。**

## 诊断方法论（可复用到任意魔改内核）

- **结构体偏移定位**：`/proc/kallsyms` 取函数地址 → 从 vmlinux 镜像按 `_text` 偏移取机器码
  → `llvm-objcopy -I binary -O elf32-littlearm` + `llvm-objdump` 反汇编 → 找 `str/ldr/add`
  的立即数即字段偏移；多函数交叉验证防误判。
- **活体布局扫描**：模块内引用导出符号（如 `contig_page_data`），扫描其内存中的自引用指针，
  恢复真实偏移（本仓库 `patch_official.py` 留有探针代码）。
- **自己产物的布局**：CI 里 `apt install dwarves && pahole -C net_device r8152.ko`。
- **崩溃现场**：`echo N > /proc/sys/kernel/panic` 后加载危险模块，panic 自动重启；
  `/sys/fs/pstore/dmesg-ramoops-*` 留有完整 Oops 现场。
- **排除内存不足**：`/proc/zoneinfo`（pages free vs min 水位）+ `/proc/pagetypeinfo`（按迁移类型）。
- **dmesg 噪音**：视频解码盒子会被 `vdec`/`is_reset` 日志刷屏，grep 时记得排除。

## 构建

### GitHub Actions（推荐）

push 即构建：安装 `gcc-arm-linux-gnueabihf` → 下载 `linux-4.9.113.tar.xz` → `box.config`
打开 `CONFIG_USB_RTL8152=m` → `modules_prepare` → 真实 CRC 表（`Module.symvers`）→
`make M=drivers/net/usb modules` → 产物已自动完成 vermagic 改写与 strip。
另产出 `out/iperf3-static`（ARM 静态 iperf3，用于带宽测试）。

### 手动

```bash
python3 patch_official.py     # 官方驱动 → 4.9 兼容 + get_zeroed_page RX 缓冲
python3 patch_netdevice.py    # netdevice.h 布局对齐（+8 字节 padding）
# ... 按 build.yml 的步骤编译
python3 patch_vermagic.py     # 产物 vermagic 4.9.113 → 4.9.y 就地改写
```

## 安装到盒子

```sh
# 模块放 /vendor（持久）
mount -o remount,rw /vendor
cp /data/r8152.ko /vendor/lib/modules/r8152.ko

# 开机自动加载：在 /vendor/etc/init/hw/init.amlogic.board.rc 的 on early-boot 段加
#     insmod /vendor/lib/modules/r8152.ko

# IP 自动配置：/vendor/bin/r8152_boot.sh（本仓库提供）+ 对应 service 定义
mount -o remount,ro /vendor
```

详细 rc 片段见 `r8152_boot.sh` 头部注释。原始 rc 改前务必备份。

## 盒子上的测试工具

| 文件 | 用途 |
|---|---|
| `stability_watch.sh` | 每 10s 采样 carrier/speed/rx/tx/错误计数/网关连通/MemFree → `stability.log` |
| `stress_test.sh` | 循环拉取 100MB 测吞吐 → `stress.log`（默认 30 轮） |
| `r8152_boot.sh` | 开机 IP 配置（`ip addr add` + `link set up`，等接口出现最多 30s） |

> 脚本中的 `192.168.6.x` 是示例环境（网关/测速源），按你的局域网修改。

## 已知限制

- USB 2.0 口吞吐上限 ~280Mbps（USB 2.0 物理特性，非驱动问题）；跑满千兆需 USB 3.0 口。
- eth1 默认无网关时不能上外网；由 Android EthernetManager DHCP 接管后自动完整配置。
- 盒子 IP 由 DHCP 动态分配，ADB 走任意在线接口。
- iperf.fr 的 Android 下载链接已失效；本仓库 CI 自行交叉编译静态 iperf3。

## 文件清单

| 文件 | 说明 |
|---|---|
| `patch_official.py` | 官方 r8152 v2.22.1 → 4.9/盒子适配（API 兼容 + get_zeroed_page RX 缓冲） |
| `patch_netdevice.py` | `net_device` 布局对齐（+8 字节 padding） |
| `patch_vermagic.py` | `.modinfo` vermagic 就地改写 |
| `patch_r8152.py` | （早期）4.19 内置驱动 → 4.9 头文件的 API 裁剪，已被官方驱动方案取代，留作参考 |
| `box.config` | 盒子内核配置原样保留 |
| `Module.symvers` | 从盒子 vmlinux `__kcrctab_*` 提取的真实 CRC（10124 项） |
| `r8152_boot.sh` / `stability_watch.sh` / `stress_test.sh` | 盒子端工具 |
| `.github/workflows/build.yml` | 一键 CI |
| `out/r8152.ko` | CI 最新产物（已 patch vermagic + strip） |

## License

GPL-2.0 —— 与 Linux 内核及 Realtek 官方 r8152 驱动一致。见 [LICENSE](LICENSE)。
