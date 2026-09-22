# ESP32 传感节点（sensor01）

本项目是 B 同学负责的传感节点固件。通过 Wi‑Fi 接入本地 MQTT Broker，实现模拟量采样、云端问答、视觉告警接收及状态上报。

2026-09-23：0.5.0 已烧录并通过真实双板连续 10 次告警闭环。ADS1115、LED、蜂鸣器尚未接入；下一步按 [硬件接入与采样验收](HARDWARE_ACCEPTANCE.md) 操作。详细联调见 [COLLABORATION.md](../../COLLABORATION.md)。

## 固件能力

- 设备编号固定为 `sensor01`，当前固件版本 `sensor01-fw-0.5.1`；新增 `/i2c` 离线诊断 GPIO21/22 上的 0x48–0x4B 地址。ACK 仅表示地址应答，不能确认芯片型号或校准状态。
- Wi‑Fi 每 10 秒自动重连，MQTT 每 2 秒自动重试，主循环不会因断网长时间阻塞。
- 每 30 秒向 `physlab/sensor01/status` 发布 retained 心跳，心跳中额外包含 `ads_initialized` 字段。
- 串口输入问题后向 `physlab/assistant/question` 发布 V1 JSON。
- 从 `physlab/assistant/answer` 接收相同 `request_id` 的回答并输出到串口。
- 从 `physlab/vision/result` 接收视觉异常，并向 `physlab/alarm` 发布告警。
- 订阅 `physlab/sensor01/cmd`；收到 `sample_now` 时立即执行单次采样并发布数据。
- 启动 NTP 校时；尚未同步时使用 `ts=0` 并在状态中声明 `clock_synced=false`。
- **ADS1115（I2C ADC）驱动已接入代码**，本轮未进行硬件与校准验收；默认使用 ESP32 硬件 I2C 总线：
  - SDA → GPIO 21
  - SCL → GPIO 22
  - 器件地址 → 0x48（ADDR 引脚接地）
  - 采集通道 → A0，PGA 量程 ±6.144V，单次转换模式，860 SPS
- 每 5 秒自动采样一次，数据发布到 `physlab/sensor01/data`（schema: `physlab.sensor.data.v1`）。
- ADS1115 初始化失败时会在主循环中每 5 秒重试，不阻塞其他功能。
- 蜂鸣器和 LED 暂不接入，命令中若涉及执行器则安全拒绝。

## 硬件连接

```
ESP32 Dev Module        ADS1115 模块
─────────────────────────────────────
3.3V    ──────────────── VDD
GND     ──────────────── GND
GPIO21  ──────────────── SDA
GPIO22  ──────────────── SCL
GND     ──────────────── ADDR   (默认地址 0x48)
传感器 + ──────────────── A0
传感器 - ──────────────── GND
```

> 注：若 ADDR 引脚接 VDD，则器件地址变为 0x49，需相应修改代码中的 `ADS_ADDR`。

PGA ±6.144V 是换算满量程，不是引脚允许输入电压；上述 3.3V 供电接法只接入供电轨范围内且共地的信号。实验信号需合适的限压/调理后接 ADC。

## 配置与保密

复制 `src/secrets.h.example` 为 `src/secrets.h`，填写 2.4 GHz Wi‑Fi、密码和电脑在同一局域网中的 IPv4 地址。真实文件已被 Git 忽略，禁止提交或截图传播。

电脑和 ESP32 必须处于同一普通局域网。部分校园网会启用客户端隔离，此时即使二者都能上网，也可能无法互相访问；开发联调优先使用手机 2.4 GHz 热点或允许局域网互访的路由器。

## PlatformIO 操作

在项目根目录（`esp32_board_test/`）执行：

```powershell
# 编译
& "$HOME\.platformio\penv\Scripts\platformio.exe" run --environment esp32dev

# 烧录（COM5 是本轮检测值，每次接入需核实；覆盖 ini 中的旧 COM3）
& "$HOME\.platformio\penv\Scripts\platformio.exe" run --target upload --environment esp32dev --upload-port COM5

# 串口监视器
& "$HOME\.platformio\penv\Scripts\platformio.exe" device monitor --baud 115200 --port COM5
```

烧录前核实：目标串口对应 B 板、USB 线稳定、`secrets.h` 的 Wi‑Fi 可供板子接入、MQTT 地址是可访问的服务电脑 IPv4。

## 调试与排查

**串口监视器输出示例：**
```
PhysLab sensor node starting: sensor01-fw-0.5.0
I2C initialized on SDA=21, SCL=22
ADS1115 initialized successfully.
Device address: 0x48
WiFi connected.
ESP32 IP address: 192.168.x.x
NTP synchronization requested.
MQTT connected.
Subscribed: physlab/assistant/answer
Subscribed: physlab/vision/result
Subscribed: physlab/sensor01/cmd
Status published: {...}
Sensor data published: {...}
```

**常见问题：**

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `ADS1115 initialization failed!` | I2C 接线松动 / ADDR 地址非 0x48 | 检查接线；若 ADDR 接 VDD，将代码中 `ADS_ADDR` 改为 `0x49` |
| `could not open port 'COM3': PermissionError` | 串口被其他程序占用 | 关闭串口监视器、Arduino IDE 等占用 COM3 的程序 |
| `WiFi credentials are empty` | `src/secrets.h` 未填写 | 复制 example 文件并填写 SSID/密码/MQTT 地址 |
| 无法收到 MQTT 消息 | 电脑防火墙 / 局域网隔离 | 检查防火墙规则；尝试手机热点 |

## MQTT 消息协议速查

| Topic | Schema | 说明 |
|---|---|---|
| `physlab/sensor01/status` | `physlab.sensor.status.v1` | 心跳（上行），含 online/rssi/uptime/heap/fw/ads_initialized |
| `physlab/sensor01/data` | `physlab.sensor.data.v1` | 采样数据（上行），含 channel/voltage_v/raw/calibrated |
| `physlab/sensor01/cmd` | `physlab.sensor.cmd.v1` | 控制命令（下行），支持 action=`sample_now` |
| `physlab/assistant/question` | `physlab.assistant.question.v1` | 提问（上行） |
| `physlab/assistant/answer` | `physlab.assistant.answer.v1` | 回答（下行） |
| `physlab/vision/result` | `physlab.vision.result.v1` 或旧 `physlab.vision.v1` | 视觉结果（下行） |
| `physlab/camera01/cmd` | `physlab.camera.cmd.v1` | `/capture` 拍照请求（上行） |
| `physlab/camera01/status` | `physlab.camera.status.v1` | A 上传状态（下行） |
| `physlab/alarm` | `physlab.alarm.v1` | 告警（上行） |

## 开发记录

- **2026-09-09**：B 同学接手项目，完成固件编译与烧录（fw-0.3.0），ESP32-D0WD-V3 确认连接 COM3。
- **2026-09-17**：接入 ADS1115 I2C ADC（GPIO21/22，地址 0x48），实现自动采样（5s 间隔）与数据上报，固件升级至 fw-0.4.0。
## 2026-09-17：固件 0.5.0 联调更新

- 支持 A Day08 的 `physlab.vision.result.v1`，也支持旧 `physlab.vision.v1`。
- 订阅 `physlab/camera01/status`；串口 `/capture` 触发 A 板拍照，`/sample` 发起 ADC 采样，普通文字继续实验问答。
- 相机结果等待 30 秒超时；新视觉结果最近 8 条去重；danger 映射 critical 告警。
- 保留 ADS1115 SDA=21/SCL=22/地址0x48/A0 配置，改用有超时的转换状态轮询，重新连上 ADC 时重新设置量程和采样率。
- 电压统一为 `voltage_v`，附 raw、range_v、calibrated=false，未校准数据 quality=degraded。
- 执行器引脚未核实，输出仍是串口与 MQTT 告警，不驱动 LED、蜂鸣器或继电器。
- 已编译通过，未烧录；当前识别到 B 板为 COM5，旧 platformio.ini 仍保留 COM3。核实网络配置后，可在 PlatformIO 选择当前端口，或上传时指定 `--upload-port COM5`。

双人操作流程见 [COLLABORATION.md](../../COLLABORATION.md)。
