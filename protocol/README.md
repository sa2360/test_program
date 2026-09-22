# PhysLab MQTT 协议 V1

本目录是双板、边缘电脑和云端服务之间的唯一协议来源，由 B 同学维护。

## 2026-09-17 双人联调兼容约定

A 的 Day08 实测格式与旧 B V1 有差异。本次采用显式兼容：

- 新电脑端结果使用 `physlab.vision.result.v1`，定义在 `schemas/vision.result.ab.v1.schema.json`；字段为 `result/scene/warnings/suggestion`，对应 A 交接说明。
- 旧 `physlab.vision.v1` 和 `warning/message` 仍可接收，定义保留在 `vision.result.v1.schema.json`。B 固件 0.5.0 同时支持两种格式。
- `camera.status.v1` 接受 A 的 `heap/psram`、无 `ts` 状态和失败状态；旧 `heap_bytes/ts` 仍有效。负 `http_status` 表示 ESP32 HTTPClient 的传输错误，不是 HTTP 响应码。
- 相机命令 `ts` 改为可选。新发送端仍填写；A Day08 的命令样例可直接使用。
- `sensor.status` 增加可选 `ads_initialized`；采样仍以 **伏特 `voltage_v`** 为公共单位，新增可选 `raw/channel/range_v/calibrated/request_id`。未校准采样使用 `quality=degraded`。
- `danger` 对应统一告警 `level=critical`；`unknown` 表示没有识别结论。`ok` 不允许携带告警。
- `source=unconfigured/manual/model` 分别表示未配置模型、人工复核、模型输出。当前图片服务只实现前两者。
- 图片上传上限 2 MiB，像素上限 400 万；JSON 结果上限 16 KiB。请求 ID 使用 1–96 位英文字母、数字、点、横线或下划线。
- 命令、状态事件和视觉结果使用 `retain=false`；只有设备在线心跳适合保留消息。A Day08 发布状态为 QoS 0，电脑工具和服务为 QoS 1，不能把 Broker 确认当成设备处理确认。
- 幂等窗口：图片/结果在电脑 SQLite 索引内持久化；B 新视觉结果保留最近 8 条指纹，重启后清空。A Day08 仅记住最近一个拍照 ID，需要 A 后续加强重试处理。

完整 HTTP 说明和联调步骤见 [双人开发与联调](../COLLABORATION.md)。

## 冻结规则

- MQTT 主题使用小写英文，设备编号固定在路径中。
- 消息编码统一为 UTF-8 JSON。
- `schema` 必须使用 `physlab.<message>.v1`。
- 时间字段统一为 Unix 毫秒 `ts`；设备时钟未同步时允许为 `0`，并在状态消息中令 `clock_synced=false`。
- 跨节点流程必须复用同一个 `request_id`，禁止重新生成。
- 未列出的字段默认不允许；协议变更必须新增版本或保持向后兼容。
- QoS 1 消息可能重复，接收端必须按 `request_id` 幂等处理。

## V1 主题

| 主题 | 方向 | QoS | Schema | 用途 |
|---|---|---:|---|---|
| `physlab/sensor01/data` | B板 -> 服务 | 0 | `physlab.sensor.data.v1` | 传感器周期数据 |
| `physlab/sensor01/status` | B板 -> 服务 | 1 | `physlab.sensor.status.v1` | 在线状态与心跳 |
| `physlab/sensor01/cmd` | 服务 -> B板 | 1 | `physlab.sensor.cmd.v1` | 采样和执行器命令 |
| `physlab/camera01/cmd` | 服务 -> A板 | 1 | `physlab.camera.cmd.v1` | 拍照命令 |
| `physlab/camera01/status` | A板 -> 服务 | 1 | `physlab.camera.status.v1` | 摄像头和上传状态 |
| `physlab/vision/result` | 边缘端 -> B板 | 1 | `physlab.vision.v1` | YOLO/占位识别结果 |
| `physlab/assistant/question` | B板/电脑 -> 云端 | 1 | `physlab.assistant.question.v1` | 实验问答请求 |
| `physlab/assistant/answer` | 云端 -> B板/电脑 | 1 | `physlab.assistant.answer.v1` | 实验问答结果 |
| `physlab/alarm` | 双向 | 1 | `physlab.alarm.v1` | 统一告警事件 |

## 目录

- `schemas/`：可由 Python 自动测试使用的 JSON Schema。
- `error_codes.md`：冻结的错误码和处理原则。
