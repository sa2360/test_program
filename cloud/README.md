# B 同学云端服务

2026-09-17 已进入 A/B 联合开发，新增图片接收与结果回传。请先看 [双人联调说明](../COLLABORATION.md) 和 [最新进度](../STATUS.md)。

本目录负责 MQTT 消息接入、V1 协议校验、RLC 本地知识检索、Agnes AI 问答以及模拟联调。

## 已完成能力

- 订阅 `physlab/assistant/question`，校验 JSON Schema 后生成回答。
- 发布 `physlab/assistant/answer`，原样保留 `request_id` 供全链路追踪。
- Agnes 正常时使用 `agnes-2.0-flash`；接口超时或断网时自动回退到本地知识库。
- 关闭 SDK 隐式重试，避免网络异常时多次等待；超时时间由 `LLM_TIMEOUT_SECONDS` 控制。
- 本地没有匹配资料时使用安全固定回答，不让 MQTT 服务因模型异常退出。
- 提供视觉结果模拟器和一次性主题监听器。
- 完整协议和错误码见 `../protocol/README.md`。

本地 RLC 资料当前标记为 `pending_physics_review`，在物理专业同学复核前不能作为最终实验结论来源。

## 首次安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

复制 `.env.example` 为 `.env`，仅在本机填写 Agnes 密钥。禁止提交 `.env` 或在截图中暴露密钥。

```dotenv
LLM_ENABLED=true
AGNES_API_KEY=你的密钥
LLM_BASE_URL=https://apihub.agnes-ai.com/v1
LLM_MODEL=agnes-2.0-flash
```

## 本地运行

依次启动 Broker 和云端：

```powershell
.\.venv\Scripts\python.exe -m tools.run_broker
.\.venv\Scripts\python.exe -u -m app.main
```

另开终端验证问答：

```powershell
.\.venv\Scripts\python.exe -u -m tests.simulate_device
```

验证视觉消息：先运行监听，再在另一个终端发布模拟结果。

```powershell
.\.venv\Scripts\python.exe -u -m tools.monitor_once vision
.\.venv\Scripts\python.exe -u -m tools.mock_vision --warning inductor_missing
```

## 自动测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

测试覆盖配置读取、Agnes 兼容调用、本地知识检索、请求编号保持和 9 类 V1 消息 Schema。
## 2026-09-17：进入 A/B 联合开发

新增图片接收、结果回传和联调工具。完整启动与两人分工见 [COLLABORATION.md](../COLLABORATION.md)，最新验收见 [STATUS.md](../STATUS.md)。上方问答服务说明仍适用。

在本目录运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tools.check_joint_loop
```

图片服务入口为 `app.image_server:app`，与 A 的 `/api/v1/images` 接口兼容；Agnes 问答仍由 `app.main` 提供。图片未配置视觉模型时返回 unknown。
