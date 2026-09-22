# PhysLab V1 错误码

| 错误码 | 产生端 | 含义 | 接收端动作 |
|---|---|---|---|
| `invalid_json` | 任意接收端 | JSON 无法解析 | 丢弃消息并记录原始主题 |
| `unsupported_schema` | 任意接收端 | Schema 版本不受支持 | 拒绝执行，提示升级 |
| `missing_request_id` | 命令/结果接收端 | 缺少链路标识 | 拒绝执行并发布 `protocol_error` |
| `protocol_error` | 任意接收端 | 字段、类型或枚举值不符合 V1 | 拒绝执行并记录原因 |
| `mqtt_disconnected` | 设备端 | MQTT 离线 | 保持本地保护并后台重连 |
| `sensor_read_error` | B板 | 传感器读取失败 | 标记数据无效，不生成物理结论 |
| `vision_timeout` | 边缘/B板 | 等待视觉结果超时 | 提示视觉不可用，本地采样继续 |
| `inductor_missing` | 视觉端 | 未检测到电感 | B板短鸣/显示提示 |
| `camera_capture_failed` | A板 | 拍照失败 | 上报状态，有限次数重试 |
| `image_upload_failed` | A板/API | 图片上传失败 | 5xx/超时最多重试两次；4xx不盲目重试 |
| `llm_unavailable` | 云端 | 大模型调用失败 | 返回降级回答，MQTT 服务继续运行 |

