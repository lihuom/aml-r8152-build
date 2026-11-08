# aml-r8152-build

Realtek RTL8153B USB 千兆网卡驱动（官方 v2.22.1），适配 Amlogic S905L3A Android 9 盒子（MECOOL KM9 Pro，内核 4.9.113 armv7）。GitHub Actions 一键构建，产物可直接 insmod。

## 测试环境

| 项目 | 说明 |
|---|---|
| 设备 | MECOOL KM9 Pro（S905L3A，Android 9） |
| 内核 | 4.9.113 armv7（Amlogic 魔改版，modversions 强校验） |
| 网卡 | RTL8153B USB 千兆（0bda:8153），插 USB 2.0 口 |
| 结果 | 千兆协商、DHCP 自动联网、3GB 压测 30/30 轮零错误，峰值 280Mbps（USB 2.0 上限），零内核崩溃 |

> 盒子内核与主线 4.9 有多处结构布局差异（net_device / pglist_data），补丁已处理，细节见 patch 脚本内注释。

## 使用

### 1. 获取驱动

CI 产物 `out/r8152.ko`（已改写 vermagic、已 strip），或按 `.github/workflows/build.yml` 手动构建。

### 2. 安装到盒子

```sh
adb push r8152.ko /data/r8152.ko
adb shell '
  mount -o remount,rw /vendor
  cp /data/r8152.ko /vendor/lib/modules/r8152.ko
  # 在 /vendor/etc/init/hw/init.amlogic.board.rc 的 on early-boot 段加一行：
  #   insmod /vendor/lib/modules/r8152.ko
  mount -o remount,ro /vendor
  insmod /vendor/lib/modules/r8152.ko
  ip link set eth1 up
'
```

开机自动配 IP：把 `r8152_boot.sh` 放到 `/vendor/bin/`（755 权限），并把 `append.rc` 的内容追加到上面 rc 文件末尾。

### 3. 测试工具

| 脚本 | 用途 |
|---|---|
| `stability_watch.sh` | 每 10s 采样链路/错误计数/内存 → `stability.log` |
| `stress_test.sh` | 循环拉 100MB 测吞吐 → `stress.log`（默认 30 轮） |

> 脚本里的 `192.168.6.x` 按你的局域网修改（网关、HTTP 下载源）。

## 重新构建

```sh
python3 patch_official.py    # 官方驱动 → 4.9/盒子适配
python3 patch_netdevice.py   # net_device 布局对齐
python3 patch_vermagic.py    # 产物 vermagic 改写
# 其余步骤见 .github/workflows/build.yml
```

## License

GPL-2.0（与 Linux 内核及 Realtek 官方驱动一致）
