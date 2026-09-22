# 大学物理实验智能辅助系统

当前为 A/B 两人共同开发阶段。A 负责 ESP32-S3-CAM 拍照上传；B 负责经典 ESP32 的采样、消息处理，以及电脑端服务集成。

先看 [STATUS.md](STATUS.md) 了解已经验证的内容，再按 [COLLABORATION.md](COLLABORATION.md) 进行联调。

| 目录/文件 | 内容 | 主要维护者 |
|---|---|---|
| `device/esp32_board_test` | B 板 PlatformIO 工程 | B |
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
