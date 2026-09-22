# A 同学视觉节点 Day08 交接说明

项目：大学物理实验多模态智能助手
节点：ESP32-S3-CAM 视觉节点
设备 ID：`camera01`
当前状态：A 板已完成独立闭环测试，可进入 A/B 联合开发阶段。

------

## 1. A 板当前已经完成的能力

A 板现在已经可以完成以下完整流程：

```
MQTT 接收拍照命令
↓
ESP32-S3-CAM 拍摄 JPEG 图片
↓
通过 HTTP POST 上传图片到服务器
↓
服务器保存图片并返回 image_id
↓
A 板通过 MQTT 发布上传状态
```

也就是说，A 板现在已经具备“远程触发拍照 + 图片上传 + 状态回传”的能力。

------

## 2. Day08 实测结果

### 2.1 请求编号

```
request_id: req-day08-001
```

### 2.2 ESP32 拍照结果

```
ESP32 JPEG bytes: 12345
Capture time: 1 ms
Free Heap: 265176
Free PSRAM: 8306911
```

### 2.3 服务器上传结果

```
HTTP status: 201 Created
received_bytes: 12345
image_id: img-88b75b24c5dc
file: uploads\req-day08-001_img-88b75b24c5dc.jpg
```

### 2.4 MQTT 状态结果

```
MQTT state: uploaded
result: success
```

### 2.5 图片人工验证

```
上传图片是否可打开：是
画面是否与实际场景一致：是
```

结论：

```
A 板 Day08 独立链路跑通。
MQTT 命令、摄像头拍照、HTTP 上传、服务器存图、MQTT 状态回传全部正常。
```

------

# 3. A 板使用的 MQTT Topic

## 3.1 A 板订阅的命令 Topic

B 同学或电脑端如需触发 A 板拍照，需要向以下 Topic 发布命令：

```
physlab/camera01/cmd
```

------

## 3.2 A 板发布的状态 Topic

A 板拍照和上传完成后，会向以下 Topic 发布状态：

```
physlab/camera01/status
```

B 同学如需知道 A 板是否上传成功，需要订阅这个 Topic。

------

# 4. 触发 A 板拍照的命令格式

向：

```
physlab/camera01/cmd
```

发布以下 JSON：

```
{
  "schema": "physlab.camera.cmd.v1",
  "request_id": "req-day08-001",
  "action": "capture",
  "resolution": "VGA",
  "jpeg_quality": 15,
  "timeout_ms": 15000
}
```

------

## 字段说明

| 字段           | 含义                                         |
| -------------- | -------------------------------------------- |
| `schema`       | 协议版本，当前固定为 `physlab.camera.cmd.v1` |
| `request_id`   | 本次请求编号，用于 A/B/服务器三方对齐        |
| `action`       | 操作类型，目前固定为 `capture`               |
| `resolution`   | 拍照分辨率，目前实测为 `VGA`                 |
| `jpeg_quality` | JPEG 压缩质量，当前使用 `15`                 |
| `timeout_ms`   | 超时时间，当前使用 `15000` ms                |

------

# 5. A 板上传成功后的状态格式

A 板上传成功后，会向：

```
physlab/camera01/status
```

发布：

```
{
  "schema": "physlab.camera.status.v1",
  "device_id": "camera01",
  "request_id": "req-day08-001",
  "state": "uploaded",
  "image_id": "img-88b75b24c5dc",
  "bytes": 12345,
  "http_status": 201,
  "heap": 265176,
  "psram": 8306911,
  "error": null
}
```

------

## 字段说明

| 字段          | 含义                                                |
| ------------- | --------------------------------------------------- |
| `schema`      | 状态协议版本，当前固定为 `physlab.camera.status.v1` |
| `device_id`   | 摄像头设备 ID，当前为 `camera01`                    |
| `request_id`  | 与拍照命令中的请求编号一致                          |
| `state`       | 当前状态，成功时为 `uploaded`                       |
| `image_id`    | 服务器返回的图片 ID，B/服务器后续识别要用           |
| `bytes`       | ESP32 拍摄并上传的 JPEG 文件大小                    |
| `http_status` | HTTP 上传状态码，成功为 `201`                       |
| `heap`        | ESP32 当前剩余堆内存                                |
| `psram`       | ESP32 当前剩余 PSRAM                                |
| `error`       | 错误信息，成功时为 `null`                           |

------

# 6. 服务器端上传日志

服务器已成功收到 A 板上传的图片。

日志如下：

```
uploaded request_id=req-day08-001 device_id=camera01 bytes=12345 file=uploads\req-day08-001_img-88b75b24c5dc.jpg
INFO:     172.20.10.9:64436 - "POST /api/v1/images HTTP/1.1" 201 Created
```

说明：

```
服务器接口 /api/v1/images 正常。
HTTP POST 上传正常。
服务器已保存图片。
服务器返回 image_id 正常。
```

------

# 7. A 板串口日志

```
MQTT message received. topic=physlab/camera01/cmd length=163
Handling capture request: req-day08-001
Captured: bytes=12345 time=1 ms heap=265616 psram=8309239
Upload success: image_id=img-88b75b24c5dc received_bytes=12345
Status publish: state=uploaded result=success
{"schema":"physlab.camera.status.v1","device_id":"camera01","request_id":"req-day08-001","state":"uploaded","image_id":"img-88b75b24c5dc","bytes":12345,"http_status":201,"heap":265176,"psram":8306911,"error":null}
```

结论：

```
A 板没有重启。
PSRAM 正常。
MQTT 正常。
拍照正常。
上传正常。
状态发布正常。
```

------

# 8. MQTTX 实测截图说明

MQTTX 中已经完成：

1. 向 `physlab/camera01/cmd` 发布拍照命令；
2. A 板收到命令；
3. A 板上传图片；
4. A 板向 `physlab/camera01/status` 返回 `uploaded` 状态。

实测状态：

```
Topic: physlab/camera01/status
state: uploaded
image_id: img-88b75b24c5dc
http_status: 201
```

------

# 9. 图片结果

A 板上传的图片已能正常打开，画面与实际摄像头场景一致。

当前图像验证结果

```
图片可打开：是
画面与实际场景一致：是
JPEG 上传未损坏：是
```

------

# 10. 给 B 同学的对接重点

B 同学接下来主要不需要关心 A 板内部怎么拍照，只需要关心两个 Topic：

## 10.1 如果 B 要触发 A 拍照

发布命令到：

```
physlab/camera01/cmd
```

命令格式：

```
{
  "schema": "physlab.camera.cmd.v1",
  "request_id": "req-b-001",
  "action": "capture",
  "resolution": "VGA",
  "jpeg_quality": 15,
  "timeout_ms": 15000
}
```

注意：

```
request_id 每次要不同。
建议格式：req-b-001、req-b-002、req-b-003。
```

------

## 10.2 如果 B 要监听 A 上传状态

订阅：

```
physlab/camera01/status
```

收到：

```
{
  "state": "uploaded",
  "image_id": "xxx",
  "request_id": "xxx"
}
```

说明 A 板已经完成图片上传。

------

# 11. B 同学后续应该做什么

B 同学接下来应该完成：

```
订阅 A 板状态
↓
拿到 image_id 和 request_id
↓
等待或接收电脑端/服务器视觉识别结果
↓
根据识别结果控制蜂鸣器、LED、继电器或其他执行器
```

------

# 12. 推荐的联合开发完整链路

最终建议按下面这条链路完成：

```
B板或电脑端发布拍照命令
        ↓
A板订阅 physlab/camera01/cmd
        ↓
A板拍照并上传服务器
        ↓
A板发布 physlab/camera01/status
        ↓
服务器根据 image_id 找到图片并运行视觉识别模型
        ↓
服务器发布识别结果 topic
        ↓
B板接收识别结果
        ↓
B板执行提示/报警/显示
```

------

# 13. 下一阶段建议新增的视觉识别结果 Topic

建议服务器或电脑端将 YOLO/视觉模型结果发布到：

```
physlab/vision/result
```

B 同学订阅这个 Topic。

------

## 推荐识别结果 JSON 格式

```
{
  "schema": "physlab.vision.result.v1",
  "request_id": "req-day08-001",
  "image_id": "img-88b75b24c5dc",
  "device_id": "camera01",
  "result": "ok",
  "scene": "rlc_series",
  "objects": [
    {
      "name": "oscilloscope",
      "confidence": 0.92
    },
    {
      "name": "signal_generator",
      "confidence": 0.88
    }
  ],
  "warnings": [],
  "suggestion": "实验器材识别正常，可以继续下一步操作。"
}
```

------

# 14. 如果识别到异常，建议格式如下

```
{
  "schema": "physlab.vision.result.v1",
  "request_id": "req-b-002",
  "image_id": "img-xxxx",
  "device_id": "camera01",
  "result": "warning",
  "scene": "rlc_series",
  "objects": [
    {
      "name": "resistor",
      "confidence": 0.91
    },
    {
      "name": "capacitor",
      "confidence": 0.89
    }
  ],
  "warnings": [
    {
      "level": "warning",
      "code": "WIRE_MISSING",
      "message": "疑似缺少一根连接导线，请检查 RLC 串联回路是否闭合。"
    }
  ],
  "suggestion": "请检查电阻、电感、电容是否已串联，并确认信号源输出端与示波器测量端连接正确。"
}
```

------

# 15. B 板建议处理逻辑

B 板可以按 `result` 字段进行动作：

| result    | 含义               | B 板动作              |
| --------- | ------------------ | --------------------- |
| `ok`      | 正常               | 绿灯亮/短提示音       |
| `warning` | 有风险或疑似错误   | 黄灯亮/蜂鸣器短响     |
| `danger`  | 严重错误或安全风险 | 红灯亮/蜂鸣器长响     |
| `unknown` | 无法识别           | 蓝灯闪烁/提示重新拍摄 |

------

# 16. B 板需要订阅的 Topic

建议 B 板至少订阅：

```
physlab/camera01/status
physlab/vision/result
```

其中：

```
physlab/camera01/status
```

用于确认 A 板图片是否上传成功。

```
physlab/vision/result
```

用于接收服务器或电脑端模型识别结果。

------

# 17. 联调第一步建议

第一步不要直接上复杂模型，建议先用 MQTTX 人工模拟视觉识别结果。

## 操作流程

### 第一步：B 板订阅

```
physlab/vision/result
```

### 第二步：用 MQTTX 发布正常结果

Topic：

```
physlab/vision/result
```

Payload：

```
{
  "schema": "physlab.vision.result.v1",
  "request_id": "req-b-test-001",
  "image_id": "img-test-001",
  "device_id": "camera01",
  "result": "ok",
  "scene": "rlc_series",
  "objects": [],
  "warnings": [],
  "suggestion": "识别正常，可以继续实验。"
}
```

B 板预期动作：

```
绿灯亮，或蜂鸣器短响一次。
```

------

### 第三步：用 MQTTX 发布 warning 结果

Topic：

```
physlab/vision/result
```

Payload：

```
{
  "schema": "physlab.vision.result.v1",
  "request_id": "req-b-test-002",
  "image_id": "img-test-002",
  "device_id": "camera01",
  "result": "warning",
  "scene": "rlc_series",
  "objects": [],
  "warnings": [
    {
      "level": "warning",
      "code": "WIRE_MISSING",
      "message": "疑似接线缺失，请检查回路。"
    }
  ],
  "suggestion": "请检查 RLC 串联电路是否闭合。"
}
```

B 板预期动作：

```
黄灯亮，或蜂鸣器短响多次。
```

------

### 第四步：用 MQTTX 发布 danger 结果

Topic：

```
physlab/vision/result
```

Payload：

```
{
  "schema": "physlab.vision.result.v1",
  "request_id": "req-b-test-003",
  "image_id": "img-test-003",
  "device_id": "camera01",
  "result": "danger",
  "scene": "rlc_series",
  "objects": [],
  "warnings": [
    {
      "level": "danger",
      "code": "POWER_RISK",
      "message": "疑似存在错误接线或通电风险，请立即检查。"
    }
  ],
  "suggestion": "请先断开电源，再检查接线。"
}
```

B 板预期动作：

```
红灯亮，蜂鸣器长响。
```

------

# 18. 联调第二步建议

在 B 板能正确响应 `physlab/vision/result` 后，再接入 A 板和服务器。

完整流程：

```
MQTTX/B板 发布 physlab/camera01/cmd
↓
A板拍照上传
↓
A板发布 physlab/camera01/status
↓
服务器收到 uploaded 状态或根据 image_id 执行识别
↓
服务器发布 physlab/vision/result
↓
B板接收并报警
```

------

# 19. A 给 B 的最终结论

A 板已经具备以下稳定输出：

```
Topic: physlab/camera01/status
状态: uploaded
核心字段: request_id, image_id, bytes, http_status
```

B 板接下来只需要围绕

```
physlab/vision/result
```

开发执行器响应逻辑。

如果 B 板需要主动触发拍照，则发布：

```
physlab/camera01/cmd
```

即可。

------

# 20. 当前联合开发分工建议

## A 同学继续负

```
1. 保持 A 板在线
2. 提供 camera01 拍照上传服务
3. 协助排查 MQTT/HTTP 上传问题
4. 后续根据需要调整分辨率、画质、拍照角度
```

------

## B 同学负责

```
1. ESP32 传感控制节点接入 MQTT
2. 订阅 physlab/vision/result
3. 解析 JSON 识别结果
4. 根据 result 控制 LED/蜂鸣器/继电器
5. 可选：发布 physlab/camera01/cmd 主动触发拍照
```

------

## 电脑端/服务器负责

```
1. 接收 A 板上传的图片
2. 根据 image_id 找到图片文件
3. 运行最小视觉模型
4. 生成识别结果 JSON
5. 发布到 physlab/vision/result
```

------

# 21. 最终系统目标

联合开发完成后，系统应形成以下闭环：

```
实验台画面
↓
A板拍照
↓
服务器识别
↓
B板报警/提示
↓
学生根据提示修改实验操作
```

这就是项目从 A 板独立开发进入双板协同开发的对接基础。