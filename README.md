# 大学物理实验智能辅助系统

当前为 A/B 两人共同开发阶段。A 负责 ESP32-S3-CAM 拍照上传；B 负责经典 ESP32 的采样、消息处理，以及电脑端服务集成。

## 最新进度（2026-09-23 更新）

保留其他任务新增的学生端、教师端、实验数据表、问答和三类实验知识库。2026-09-23 已恢复热点并完成真实双板闭环；设备在线状态仍应以当前心跳为准。

- **A 板实物拍照通过**：ESP32-S3（COM6，16 MB Flash、8 MB PSRAM）固件编译、烧录和校验成功；连续 10 次拍照均完成 JPEG 上传、MQTT `uploaded` 状态和相同请求/图片编号的视觉结果回传。轮流覆盖 RLC 串联、RLC 暂态、惠斯通电桥三种实验归属。证据见本机 `cloud/data/acceptance/camera-10.json`，图片保存在 `cloud/data/images`。
- **真实双板闭环通过（2026-09-23）**：保留 B 板已有 `sensor01-fw-0.5.0`，确认在线心跳和 NTP 同步。连续 10 次均完成 A 拍照上传 → 电脑结果回传 → B 发布 `vision_unknown` 告警，三类消息的请求编号一致；三种实验归属均正确。单次验收耗时 0.625–1.062 秒。完整证据：[joint-20260923.json](cloud/data/acceptance/joint-20260923.json)。
- **软件验证通过**：40 项 Python 自动测试（含新增采样工具的请求关联、缺模块告警和无效数据检查）通过；此前六阶段 MQTT/HTTP 集成自检通过。网页实测确认切换学生后清空旧数据表，输入原学生编号可恢复已有记录。
- **已修复**：网页拍照所选实验与图片归属不一致；切换学生时旧数据表残留及异步加载覆盖；知识库仅因实验相同而命中无关问题；中文连续文本检索；A 板 MQTT 重连阻塞 Wi-Fi 恢复、默认 256 字节 MQTT 缓冲区不足。待审核知识的本地回答增加明确标记。
- **服务重复启动已修复**：新增 `tools.run_broker`，在 Windows 使用独占 TCP 绑定；第二个实例及使用 `SO_REUSEADDR` 的竞争监听都会被拒绝，启动错误直接退出。已用真实 socket 测试验证两种冲突方向，并以该入口完成双板验收。

### 当前边界

2026-09-23 接线后复查：零输入采样未通过。B 升级为诊断版 `sensor01-fw-0.5.1`（编译、烧录及校验通过），新增离线串口 `/i2c`；GPIO21/22 上 0x48–0x4B 均无应答（NO_ACK/code=2），仍需核对模块供电和实物接线。同时出现 MQTT 重连失败，不能沿用此前在线状态。诊断日志：`cloud/data/acceptance/i2c-20260923.log`。

下一阶段已补齐 [B 板硬件接入与采样验收](device/esp32_board_test/HARDWARE_ACCEPTANCE.md) 和 `tools.check_sensor`。用户确认 ADC 与执行器尚未接；实测 B 对主动采样返回匹配请求的 `sensor_read_error`，失败证据保存在 `cloud/data/acceptance/sensor-unconnected-20260923.json`。接好 ADS1115 后运行 `python -m tools.check_sensor --count 100`，记录原始数据和统计；当前尚未完成硬件采样或校准。

视觉模型尚未配置，结果为 `source=unconfigured/result=unknown`，人工复核为 `source=manual`。拍照验收照片目前是电脑附近画面，并非实验电路图，不能据此宣称器材或接线识别通过。ADS1115 未实物校准，LED/蜂鸣器引脚尚未核实；不驱动未知执行器。学生/教师页面是受控局域网演示版，尚无账号权限隔离。原始 Word、PDF 和 A Day08 交接快照保留；`.git` 仍不是完整可用仓库，没有提交或推送。

### 启动与继续验收

电脑与两板使用热点 `sa`。上次电脑地址为 `192.168.43.86`，每次重连需重新核对，密码仅保存在本地 `secrets.h`，不写入文档。以下命令从 `cloud` 目录、不同终端运行，每个服务只启动一次：

```powershell
.\.venv\Scripts\python.exe -m tools.run_broker
.\.venv\Scripts\python.exe -m uvicorn app.image_server:app --host 0.0.0.0 --port 8000
# B 板串口问答需要这个独立服务；网页问答由上面的 HTTP 服务提供。
.\.venv\Scripts\python.exe -u -m app.main
```

学生端：<http://127.0.0.1:8000/student>；教师端：<http://127.0.0.1:8000/teacher>；健康状态：<http://127.0.0.1:8000/health>。

```powershell
# 两块实物板在线后：要求 A 上传、视觉结果、B 的 vision_unknown 告警全部关联成功。
.\.venv\Scripts\python.exe -m tools.check_physical_loop --output data/acceptance/joint-latest.json
# 仅验收 A 板拍照链路，不代表 B 告警通过；禁止同时运行相机模拟器。
.\.venv\Scripts\python.exe -m tools.check_physical_loop --camera-only --output data/acceptance/camera-latest.json
```

下一步：确认 ADS1115 接线与校准、执行器 GPIO → 收集固定实验场景及人工标签 → 接入真实视觉模型。相机可维护工程为 `device/physlab-camera-node`，原始快照仍在 `handoff/a_day08`。

先看 [STATUS.md](STATUS.md) 了解已经验证的内容，再按 [COLLABORATION.md](COLLABORATION.md) 进行联调。

| 目录/文件 | 内容 | 主要维护者 |
|---|---|---|
| `device/esp32_board_test` | B 板 PlatformIO 工程 | B |
| `device/physlab-camera-node` | A 板可维护工程，已修复 USB 日志和 MQTT 恢复/缓冲区 | A/B |
| `handoff/a_day08` | A 已交接源码及实测图片快照 | A 提供、B 对照 |
| `cloud/app` | MQTT 问答、图片接收、结果回传 | B |
| `cloud/tools` | 拍照触发、模拟 A 板、人工复核、集成检查 | B |
| `protocol` | 两人共同遵守的 JSON 协议 | B 维护，A/B 共同确认 |
| `cloud/knowledge` | 已整理的实验问答知识 | B 集成，物理专业同学复核 |
| `tasks`、根目录 Word | 原始分工、申请书及实验资料 | 两人共同维护 |

一条联调链路是：电脑或 B 板发拍照命令 → A 板上传 JPEG → 电脑登记图片并回传结果 → B 板显示结果、发布告警。图片上传成功时，若还没有模型，结果是 `unknown`。当前并未实现自动接线正确性判定。

电脑端可以运行确定性的自动检查：

```powershell
Set-Location 'D:\CodexProject\大创\cloud'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tools.check_joint_loop
```

第二个命令使用临时端口和临时数据库，读取 A 交接的 JPEG，不调用付费大模型，不要求真实开发板在线，完成后自动停止测试服务。
