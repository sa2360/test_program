"""Trigger A's camera and wait for the matching vision result."""
import argparse
import json
import threading
import uuid

import paho.mqtt.client as mqtt
from jsonschema import ValidationError

from app.config import Settings
from app.protocol import CAMERA_COMMAND_TOPIC, CAMERA_STATUS_TOPIC, VISION_RESULT_TOPIC, unix_ms, validate_message
from app.vision_protocol import normalize_vision


def main():
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="触发 A 板拍照并等待相同 request_id 的结果")
    parser.add_argument("--host", default=settings.mqtt_host)
    parser.add_argument("--port", type=int, default=settings.mqtt_port)
    parser.add_argument("--request-id", default=f"capture-{uuid.uuid4().hex[:16]}")
    parser.add_argument("--timeout", type=float, default=35)
    args = parser.parse_args()
    ready, complete = threading.Event(), threading.Event()
    answers = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"capture-{uuid.uuid4().hex[:8]}")

    def connected(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe([(CAMERA_STATUS_TOPIC, 1), (VISION_RESULT_TOPIC, 1)])

    def subscribed(client, userdata, mid, reasons, properties):
        if all(not reason.is_failure for reason in reasons):
            ready.set()

    def received(client, userdata, message):
        try:
            data = json.loads(message.payload)
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            if data.get("request_id") != args.request_id:
                return
            if message.topic == CAMERA_STATUS_TOPIC:
                validate_message("camera.status.v1.schema.json", data)
                print(f"A板状态: {data['state']}, image_id={data['image_id']}", flush=True)
            else:
                data = normalize_vision(data)
                answers.append(data)
                complete.set()
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            print(f"忽略无效消息: {type(exc).__name__}", flush=True)

    client.on_connect, client.on_subscribe, client.on_message = connected, subscribed, received
    try:
        client.connect(args.host, args.port, 30)
        client.loop_start()
        if not ready.wait(5):
            raise SystemExit("MQTT 订阅未成功")
        payload = {"schema": "physlab.camera.cmd.v1", "request_id": args.request_id,
                   "ts": unix_ms(), "action": "capture", "resolution": "VGA",
                   "jpeg_quality": 15, "timeout_ms": 15000}
        validate_message("camera.cmd.v1.schema.json", payload)
        delivery = client.publish(CAMERA_COMMAND_TOPIC, json.dumps(payload), qos=1, retain=False)
        delivery.wait_for_publish(5)
        if not delivery.is_published():
            raise SystemExit("拍照命令未确认送达 Broker")
        print(f"已发拍照命令: {args.request_id}", flush=True)
        if not complete.wait(args.timeout):
            raise SystemExit("等待视觉结果超时：检查 A 板、上传地址及图片服务。")
        print(json.dumps(answers[0], ensure_ascii=False, indent=2), flush=True)
        print("链路完成。unknown 表示尚未识别；并不表示实验接线正确。", flush=True)
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
