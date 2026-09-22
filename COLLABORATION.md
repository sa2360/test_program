# A/B 双人开发与联合调试

更新：2026-09-17。本文件针对当前文件夹中的真实代码，而非最终项目设想。

## 1. 现在到哪一步

| 环节 | 现有证据 | 本轮结果 |
|---|---|---|
| A 板拍照、HTTP 上传、MQTT 状态 | A Day08 交接说明、源码、12345 字节 JPEG | 交接格式已兼容；本轮未重测 A 实物 |
| B 板 Wi-Fi、MQTT、问答、ADS1115 | 现有 0.4.0 源码 | 改成 0.5.0，编译通过；未烧录 |
| 图片接收与索引 | A 原服务器只有存图 | 新服务增加真实 JPEG 解码、幂等、结果索引、待发消息恢复 |
| 视觉结果到 MQTT | 原来只能手动模拟消息 | HTTP 上传后返回 unknown；人工复核可发布 ok/warning/danger/unknown |
| 真实视觉模型 | 未找到训练权重和推理工程 | 待实现，不把占位输出称为识别成功 |
| 实物 LED/蜂鸣器 | 缺扩展板确认过的 GPIO 映射 | 当前串口提示 + MQTT 告警，不驱动未知引脚 |
| 新实验知识 | 三份实验 Word 已在根目录 | 还需提取、核对后纳入知识库 |

## 2. 两个人分别做什么

| 人员 | 当前负责 | 下一份可验收交付 |
|---|---|---|
| A | 摄像头、PSRAM、JPEG 质量、HTTP 上传、相机网络恢复 | 相机连接共同 Broker 和图片接口；不同 request_id 连续拍摄 10 次；提交状态、图片及失败日志 |
| B | 图片服务、Agnes/知识库、共享协议、B 板采样和结果响应 | 配置共同服务地址、烧录 0.5.0、记录拍照请求到结果与告警的对应关系；核实 ADS1115 和执行器接线 |
| A/B 共同 | 实验场景选择、器材标签、拍摄距离、验收 | 先固定一个 RLC 串联场景，收集带人工标注的真实图片，再确定模型与判定规则 |

A 的后续源码建议放独立目录，不覆盖 `device/esp32_board_test`。本轮原始交接文件保存在 `handoff/a_day08`，未改动。共同接口以 `protocol` 为准，变更时同步样例和测试。

当前 `.git` 目录没有形成可用的 Git 仓库，本轮没有生成提交或推送。现阶段用目录快照交接；建立共同仓库后，每人独立分支，只提交源码、协议、测试和文档，不提交 `.env`、`secrets.h`、`.venv`、`.pio`、原始含密码压缩包。

## 3. 网络条件

2026-09-17 实测：B 板为 COM5，芯片 ESP32-D0WD-V3；电脑接入 SCNUNET，IPv4 为 `10.242.41.15`。B 本地配置仍指向此前热点及 `192.168.43.86`。这些是检查时的地址，可能变化。

两块板必须能主动连接到服务电脑的 TCP 1883 和 8000 端口。不能只凭电脑能上网就认为板子也能访问电脑；校园网认证和终端隔离可能阻止这种访问。沿用你们允许使用、且已经验证可互访的 2.4 GHz 局域网。不要把校园网网页认证账号直接填进 ESP32 普通 Wi-Fi 密码字段。

准备联调时统一三个值：

1. A、B 都能接入的 Wi-Fi。
2. A、B 的 `MQTT_HOST` 都设置为服务电脑在该网络中的 IPv4。
3. A 的 `IMAGE_UPLOAD_URL` 设置为 `http://电脑IPv4:8000/api/v1/images`。

电脑自己访问 Broker 可保持 `127.0.0.1`。只有本机模拟工具使用 localhost；真实板子不能把电脑写成 `127.0.0.1`。当前 Broker 为无认证开发配置，只用于受控联调网络，不映射公网。

## 4. 在 VS Code 启动电脑端

打开 `cloud` 文件夹，下面三个终端都从该目录运行。首次需要安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

终端一：MQTT 中转服务。

```powershell
.\.venv\Scripts\amqtt.exe -c broker.yaml
```

终端二：兼容 A Day08 的图片服务。

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.image_server:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://127.0.0.1:8000/health`，`mqtt_connected` 应为 true；接口说明在 `/docs`。图片和 SQLite 索引默认保存在 `cloud/data/images`；可用 `IMAGE_DATA_DIR` 环境变量改变目录。一次只启动一个图片服务进程。

终端三：原有实验问答服务。它与图片链路可以独立运行。

```powershell
.\.venv\Scripts\python.exe -u -m app.main
```

Agnes 密钥仍只在本地 `.env`。本轮没有变更、打印密钥，也没有把未调用的接口标记为可用。不要给 A 同学发送带密钥的 `.env`。

## 5. 不等实物，也能双方检查接口

先运行本机完整自检：

```powershell
.\.venv\Scripts\python.exe -m tools.check_joint_loop
```

它在独立临时端口启动真实 Broker 和 HTTP 服务，验证 A Day08 JPEG、相机状态、同一 request_id 的视觉回传、重复上传、断线补发和停止服务。看到六行 PASS 和 `JOINT LOOP PASSED` 表示电脑链路通过；不代表 A/B 实物或识别准确率通过。

要手动观察，在已启动的电脑服务基础上，另开终端运行模拟 A 板：

```powershell
.\.venv\Scripts\python.exe -m tools.simulate_camera --image '..\handoff\a_day08\ESP32 Project\evidence\day08\uploaded_image_req-day08-001.jpg'
```

再开终端发一次拍照命令：

```powershell
.\.venv\Scripts\python.exe -m tools.capture_once
```

模拟 A 板与真实 A 板只运行一个，否则同一个命令会让两者同时上传。

## 6. 真实两块板怎么验收

1. A 保持当前 Day08 固件，通过本地 secrets 配置连接共同服务。当前 Day08 固件实际固定 VGA/quality=15，不会应用命令中其它分辨率和画质参数，因此联调工具固定发送这个组合。
2. B 在 VS Code 的 PlatformIO 工程中核对端口和 Wi-Fi/MQTT 配置，编译再上传 0.5.0。最新检测端口是 COM5，但每次插拔后要以实际检测为准。
3. B 打开 115200 串口监视器，确认 `MQTT connected`。发送 `/capture` 可触发 A；`/sample` 可触发一次 ADS1115 采样；普通文字仍是问答。
4. 记录 `Camera command sent [request_id]`。A 需要返回相同请求的 `uploaded`；电脑结果应携带相同 request_id 和 image_id。MQTT 结果与 A 状态先后顺序不固定，这是正常现象。
5. B 首次收到 `Vision unknown`，应提示模型未配置并发布 `vision_unknown` 告警。当前只打印串口和发布消息，不会响蜂鸣器。30 秒未等到结果则发布 `vision_timeout`。
6. 打开 `/api/v1/images` 找到 image_id；打开 `/api/v1/images/{image_id}/file` 人工查看原图。
7. 人工复核后发布结果，例如：

```powershell
.\.venv\Scripts\python.exe -m tools.review_image img-实际图片编号 --result warning --code WIRE_MISSING --message '人工复核：请检查回路连接。'
```

B 应显示 `Vision warning`，并在 `physlab/alarm` 回传告警；danger 映射为 critical。人工结果的 `source` 为 manual，不混入模型评估。

8. 在 `/api/v1/events` 查看相机状态、B 心跳、采样及告警。连续 10 次拍照均需有独立请求和正确关联；保存正常、失败、超时三类记录。
9. ADS1115 当前保留 SDA=21/SCL=22/地址0x48/A0 的已有设计。仅接入与供电电压匹配的信号，PGA ±6.144V 不是引脚耐压。未校准数据标记 degraded，不作为实验精度验收。断开 ADC 时通信应继续，不应无限等待转换。

结束时先在问答和图片终端按 Ctrl+C，再停止 Broker。联调自检已覆盖新图片服务的工作线程和连接关闭。

## 7. 图片 HTTP 接口冻结

- `POST /api/v1/images`：原始 JPEG body，`Content-Type: image/jpeg`，`X-Device-ID: camera01`，`X-Request-ID` 为请求编号；可选 `X-Experiment`，默认 rlc_series。
- 响应始终兼容 A：成功 HTTP 201，包含 image_id、request_id、received_bytes、status=queued、received_at。
- 同一请求、相同图片再次上传：HTTP 201，返回原 image_id、duplicate=true。不同图片或实验复用同一请求：HTTP 409。
- `GET /api/v1/images`：最近 20 张图片及最新处理结果。
- `GET /api/v1/images/{image_id}`：元信息和结果；`/file` 下载原 JPEG。
- `POST /api/v1/images/{image_id}/result`：人工复核结果，符合 `vision.result.ab.v1.schema.json`，request_id、image_id、scene 必须与原图片一致。
- `GET /api/v1/events`：最近 50 条合法 MQTT 事件，数据库保留最近 1000 条。
- `GET /health`：HTTP 状态、MQTT 连接状态和待发送数量。结果先入本地队列，再发布 MQTT；Broker 恢复后继续补发。

图片先保存即可返回 201，不等待视觉处理或 MQTT；因此即使 Broker 暂时不可用，图片仍有记录。初始结果为 unknown，后续人工结果可更新。同一内容复核不会重复入队。QoS 1 可能在重连边界产生重复消息，接收端需要幂等。

## 8. 后续开发优先级

1. **双板实物闭环**：共同网络、B 新固件上传、真实 A 图片、B 告警，保留请求级证据。
2. **执行器与采样验收**：A/B 提供扩展板引脚资料；B 确认 LED/蜂鸣器引脚、ADS1115 供电、量程和校准；暂不联动继电器。
3. **第一类真实视觉任务**：A 收集固定场景图片；两人确认器材标签和错误类型；B 接模型适配器。先验收器材存在性，再研究接线拓扑，器材识别不能替代接线判断。
4. **实验知识扩充**：整理根目录的惠斯通电桥、RLC 幅频特性和暂态资料，保留来源并经专业复核，再接检索问答。
5. **持续运行与项目验收**：测试网络中断、重复命令、A 重启、B 重启、模型失败、并发请求；记录误报、漏报和耗时，形成可复现的演示脚本。
