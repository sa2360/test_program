# A/B 共同开发状态

## 最新验收（2026-09-23）

- **最新接线复查（优先于以下历史在线结论）**：用户表示已接线；零输入采样请求超时。串口启动显示 ADS1115 初始化失败、MQTT 重连失败。B 编译烧录诊断版 0.5.1，增加不依赖网络的 `/i2c`；实测 SDA21/SCL22 的 0x48、0x49、0x4A、0x4B 全部 NO_ACK/code=2。已保存 `cloud/data/acceptance/i2c-20260923.log` 和失败采样报告 `sensor-zero-20260923.json`。尚未采到有效 ADC 数据，需实物接线/模块供电核对。

- 下一阶段准备：用户确认 ADS1115、LED、蜂鸣器未接；新增 `tools.check_sensor`，按 request_id 接收 A0 原始数据/失败告警，支持连续采样与可选参考电压误差检查，保存 JSON 证据。真实 B 返回 `sensor_read_error: ADS1115 is not connected.`，错误链路确认正常；不计作采样成功。接线及校准准备见 `device/esp32_board_test/HARDWARE_ACCEPTANCE.md`。

- 已重新核对其他任务新增的学生/教师页面、数据表、知识库和运行状态，保留这些成果；原始交接快照和 Word/PDF 未修改。
- 电脑及两板恢复到 `sa` 热点，电脑 IPv4 `192.168.43.86`。A 为 COM6，B 为 COM5；B 保留已烧录的 0.5.0，当前心跳 online=true、clock_synced=true、ads_initialized=false。
- **真实双板连续 10 次闭环通过**：A JPEG 上传、A `uploaded` 状态、视觉 unknown 回传、B `vision_unknown` 告警按同一 request_id 关联；三种实验归属均正确。证据：`cloud/data/acceptance/joint-20260923.json`（scope=camera_and_sensor、passed=true）。耗时 0.625–1.062 秒/次。此前仅 A 板的 10 次记录保留于 `camera-10.json`，未把早先失败覆盖成成功。
- 修复 A 的 MQTT 重连阻塞 Wi-Fi 恢复；启用原生 USB CDC 日志；MQTT 缓冲区设为 1024 字节，以容纳 UUID 请求编号的状态消息。A 编译、烧录及校验成功。
- 修复网页拍照的实验归属、切换学生的数据表残留/异步覆盖，以及本地知识无关命中和连续中文检索；待审核本地回答明确标记。
- 修复 Windows 多 Broker 同端口问题：使用 `python -m tools.run_broker` 独占绑定，旧 `amqtt.exe` 直接启动方式不再推荐。已清理上次重复实例。
- **40 项自动测试通过**（新增采样工具 4 项）；此前六阶段 MQTT/HTTP 集成自检通过，网页实际验证学生切换和原有表恢复。
- 验收结束时 `/health`：mqtt_connected=true、pending_messages=0。后台 Broker 与 HTTP 服务保留运行。

仍未完成：真实视觉模型、实验场景拍摄/标注、ADS1115 校准、执行器引脚确认、账号权限隔离及物理专业知识复核。照片当前为电脑附近画面，不代表电路识别验收。Agnes 本轮未在线验收。`.git` 不完整，未提交/推送。

---

## 前次记录（保留历史，以下不是当前结论）

更新时间：2026-09-22

## 本轮检查与完成（真实 B 板上线）

- 电脑已接入热点 `sa`（2.4 GHz，WPA2），本机 IPv4 为 `192.168.43.86`，与固件 `MQTT_HOST` 一致。
- 将 B 板 `secrets.h` 的 `WIFI_SSID` 更新为 `sa`（密码与 MQTT_HOST 不变）；`platformio.ini` 的 upload/monitor 端口由 COM3 修正为实测的 COM5。
- COM5 芯片复核：ESP32-D0WD-V3 rev v3.1。PlatformIO 编译通过（RAM 13.9%、Flash 61.6%），烧录 `sensor01-fw-0.5.0` 成功并校验。
- 启动 amqtt broker（0.0.0.0:1883）与图片服务（0.0.0.0:8000）；`/health` 返回 `mqtt_connected:true`。
- **B 板真实上线**：串口确认连接 `sa`、获取 IP `192.168.43.120`、`MQTT connected.` 并订阅三个主题；broker 日志记录来自 `192.168.43.120` 的连接；`/api/v1/events` 收到两条 B 板状态心跳，第二条 `clock_synced:true`（NTP 已同步）。
- **26 项 Python 自动测试通过**；**联调自检 6 项 PASS（JOINT LOOP PASSED）**，使用 A Day08 真实 JPEG（12345 字节）。

## 当前真实限制（2026-09-22）

- ADS1115 未接入：串口报 `ADS1115 initialization failed`，状态 `ads_initialized:false`，数据仍标 degraded。`/sample` 会触发 `sensor_read_error` 告警，属预期。
- A 板（camera01，疑似 COM6）本轮未联调：`device/physlab-camera-node/src` 缺少 A 本地 `secrets.h`，B 不覆盖 A 配置，故未烧录 A 板。真实双板闭环仍待 A 接入共同 broker 与图片接口后验证。
- 视觉模型仍未配置，图片上传默认 `result=unknown`；执行器 GPIO 未核实，仅串口提示与 MQTT 告警。
- 后台 broker 与图片服务进程仍在运行，结束联调时需先停图片服务再停 broker。

---

## 历史记录（2026-09-17）

更新时间：2026-09-17

## 本轮检查与完成

- 已检查新的 `A交接说明.md`、`落地.md` 和 `ESP32 Project(1).rar`。A Day08 已有拍照上传的交接证据；选取源码与真实 JPEG 解压到 `handoff/a_day08`，未提取密码和构建缓存。
- B 工作区已存在 ADS1115 的 0.4.0 代码。本轮沿用并修复采样协议、转换等待和重新初始化，升级为 `sensor01-fw-0.5.0`。
- 新 B 固件支持 A Day08 的视觉 JSON，也保留旧视觉 JSON；订阅相机状态；串口 `/capture` 触发 A 拍照，`/sample` 触发采样；30 秒结果超时报警；最近 8 条新格式视觉消息去重。
- 新增兼容 A 的 `POST /api/v1/images` 图片服务：真实 JPEG 解码、限额、持久化索引、幂等上传、人工复核和 MQTT 待发送队列。图片收到后默认返回明确的 unknown 结果。
- 新增拍照触发工具、模拟 A 板工具、人工复核工具和完整链路自检。
- `README.md`、`COLLABORATION.md` 已明确两人分工、启动方式、HTTP 接口、实物联调验收和后续任务。

## 本轮验证证据

- **26 项 Python 自动测试通过**：含旧问答与知识库、新 A 消息、上传限额、伪 JPEG、重复上传、请求冲突、人工结果和重启后的待发队列。
- **真实本机 MQTT + HTTP 六阶段集成检查通过**：拍照命令 → A 交接 JPEG（12345 字节）上传 → 请求/图片编号一致的结果 → 相机状态记录 → 重复上传幂等 → 断线待发结果恢复 → 安全停止。
- **B 固件编译通过**：RAM 45700/327680（13.9%），Flash 807125/1310720（61.6%）。
- **COM5 芯片检查通过**：ESP32-D0WD-V3，revision v3.1。只读取芯片信息，未烧录新固件。

## 当前真实限制

- 电脑 Wi-Fi 为 SCNUNET，IPv4 `10.242.41.15`；B 配置仍是原手机热点及 MQTT `192.168.43.86`。需统一为两板能访问的局域网服务地址，才能进行真实双板闭环。
- 本轮集成测试使用电脑模拟相机通信和 A 的真实历史 JPEG；不等于 A/B 实物当前已经联调成功。
- 当前图片服务没有训练好的视觉模型，默认 `source=unconfigured/result=unknown`；人工复核明确标记 `source=manual`，没有宣称自动识别正确接线。
- 实物 LED/蜂鸣器 GPIO 尚未核实，B 当前输出为串口提示和 MQTT 告警。ADS1115 尚未校准，数据标为 degraded。
- Agnes 本轮没有在线调用；此前网络状态不能作为今天的可用性结论。三个新增实验 Word 尚未整理进知识库。
- 当前 `.git` 无法作为有效仓库使用，本轮没有提交或推送。

下一步顺序：真实两板共同网络与烧录验收 → 执行器引脚与 ADC 校准 → 实验图片标注和真实模型 → 新实验知识入库。详细操作见 `COLLABORATION.md`。

---

## 历史记录（2026-08-01）

更新时间：2026-08-01

## 已完成

- Python 云端、MQTT Broker、Agnes AI 接口与安全回退。
- MQTT V1 主题、公共字段、错误码和 9 类 JSON Schema。
- ESP32 `sensor01` 非阻塞重连、状态心跳、串口问答、视觉告警和安全命令拒绝逻辑。
- RLC 串联实验本地知识检索（待物理专业复核）。
- 视觉结果模拟器、一次性主题监听器和 10 项自动测试。
- 云端测试全部通过；ESP32 固件 PlatformIO 编译成功。
- 本机真实 MQTT 问答与视觉消息发布/订阅测试通过。

## 当前外部条件

- Agnes 本轮实测发生网络超时，系统已成功切换到本地知识库。
- 本轮未检测到 COM3，且电脑当前 Wi‑Fi 与固件配置不一致，因此没有执行烧录，避免破坏板上现有可运行版本。
- 蜂鸣器、RGB LED、ADS1115 等硬件引脚尚未确认，下一硬件阶段需依据扩展板资料或逐项低风险实测。

## 下一阶段

1. 板子重新连接且网络匹配后，烧录 `sensor01-fw-0.3.0` 并验证心跳、问答、命令和告警。
2. 确认扩展板引脚，完成蜂鸣器/LED 安全提示。
3. 接入 ADS1115，增加原始采样、换算值、量程和校准状态。
4. A 同学接入 `camera01` 后，完成同一 `request_id` 的双板闭环。
