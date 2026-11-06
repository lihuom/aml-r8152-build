# aml-r8152-build

为 MECOOL KM9 Pro 固件（Amlogic S905L3A，Linux 4.9.113 armv7l）交叉编译 `r8152.ko`，
用于驱动 Realtek RTL8153（`0bda:8153`）USB 千兆网卡。

## 背景

目标内核 `# CONFIG_USB_RTL8152 is not set`，没有 r8152 驱动；同时
`CONFIG_MODVERSIONS=y` 且 `CONFIG_MODULE_FORCE_LOAD` 未开启，
所以外部模块必须满足：

1. `vermagic` 完全一致 —— `4.9.113 SMP preempt mod_unload modversions ARMv7`
2. `__versions` 段里每个符号的 CRC 与内核 `__kcrctab` 一致

## 文件

| 文件 | 来源 |
|---|---|
| `box.config` | 盒子 `/proc/config.gz` 解压所得，原样保留（5842 行） |
| `Module.symvers` | 从盒子 `boot` 分区解出的 vmlinux 中，按 `__kcrctab_*` 地址逐项读取的真实 CRC，共 10124 项 |

`Module.symvers` 的生成方式：解析 zImage 内的 gzip 载荷得到 24.4MB 原始内核镜像，
以 `_text = 0xc0108000` 建立虚拟地址到文件偏移的映射，再对每个
`__kcrctab_<sym>` 读取 4 字节小端值。映射已用 `__kstrtab_*` 反查符号名做过自校验。

## 流水线

`.github/workflows/build.yml` 会：

1. 安装 `gcc-arm-linux-gnueabihf`
2. 从清华镜像下载 `linux-4.9.113.tar.xz`
3. 用 `box.config` 作为 `.config`，打开 `CONFIG_USB_RTL8152=m`
4. `modules_prepare`
5. 把真实 CRC 表放到源码树根目录（供 modpost 写入 `__versions`）
6. `make M=drivers/net/usb modules`
7. 上传 `r8152.ko` 与构建日志

## 产物校验

部署前检查 `.modinfo` 中的 `vermagic`，以及 `.versions` 段的 CRC 是否与内核一致。

```
arm-linux-gnueabihf-readelf -p .modinfo r8152.ko
```
