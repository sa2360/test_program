# A 板相机工程

从 `handoff/a_day08` 的交接源码派生，原始快照不修改。本工程已在 ESP32-S3（16 MB Flash、8 MB PSRAM、原生 USB COM6）烧录验证。

复制 `include/secrets.h.example` 为 `include/secrets.h`，填写共同热点和电脑服务地址。密码文件已被根目录 `.gitignore` 排除。更换网络后重新确认电脑 IPv4；摄像头不能使用电脑的 localhost 地址。

相较交接版本：启用 USB CDC 串口日志；MQTT 缓冲区扩大到 1024 字节；每次 MQTT 重连后返回主循环，以便继续处理 Wi-Fi 恢复。摄像头仍固定 VGA、JPEG quality=15。引脚沿用交接确认的映射。

从本目录运行 PlatformIO：`pio run`，然后 `pio run -t upload --upload-port COM6`。实际端口以当次枚举为准。联合验收和限制见根目录 README；不要在真实相机运行时同时启动 `simulate_camera`。
