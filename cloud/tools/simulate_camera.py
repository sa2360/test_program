"""Use a local JPEG to exercise the exact A Day08 wire protocol."""
import argparse
import json
from pathlib import Path
import queue
import threading
import uuid

import httpx
from jsonschema import ValidationError
import paho.mqtt.client as mqtt

from app.config import Settings
from app.protocol import CAMERA_COMMAND_TOPIC, CAMERA_STATUS_TOPIC, validate_message


def main():
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="模拟 A 板；只验证通信，不模拟真实视觉识别")
    parser.add_argument("--host", default=settings.mqtt_host)
    parser.add_argument("--port", type=int, default=settings.mqtt_port)
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    image_bytes = args.image.read_bytes()
    commands = queue.Queue(maxsize=8)
    ready = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"camera-simulator-{uuid.uuid4().hex[:8]}")

    def connected(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe(CAMERA_COMMAND_TOPIC, qos=1)

    def received(client, userdata, message):
        try:
            command = json.loads(message.payload)
            validate_message("camera.cmd.v1.schema.json", command)
            commands.put_nowait(command)
        except (ValueError, ValidationError, queue.Full):
            print("模拟器忽略无效命令或忙时命令", flush=True)

    client.on_connect, client.on_message = connected, received
    client.on_subscribe = lambda c, u, m, r, p: ready.set() if all(not item.is_failure for item in r) else None
    try:
        client.connect(args.host, args.port, 30)
        client.loop_start()
        if not ready.wait(5):
            raise SystemExit("模拟器订阅失败")
        print("SIMULATOR READY: waiting for capture", flush=True)
        while True:
            command = commands.get(timeout=120 if args.once else None)
            request_id = command["request_id"]
            status = {"schema": "physlab.camera.status.v1", "device_id": "camera01",
                      "request_id": request_id, "state": "upload_failed", "image_id": "",
                      "bytes": len(image_bytes), "http_status": 0,
                      "heap": 0, "psram": 0, "error": "http_upload_failed"}
            try:
                response = httpx.post(args.server.rstrip("/") + "/api/v1/images", content=image_bytes,
                    headers={"Content-Type": "image/jpeg", "X-Device-ID": "camera01", "X-Request-ID": request_id},
                    timeout=15, trust_env=False)
                status["http_status"] = response.status_code
                response.raise_for_status()
                record = response.json()
                if response.status_code != 201 or record["request_id"] != request_id or record["received_bytes"] != len(image_bytes):
                    raise ValueError("upload response mismatch")
                status.update(state="uploaded", image_id=record["image_id"], error=None)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                print(f"模拟上传失败: {type(exc).__name__}", flush=True)
            validate_message("camera.status.v1.schema.json", status)
            delivery = client.publish(CAMERA_STATUS_TOPIC, json.dumps(status), qos=1)
            delivery.wait_for_publish(5)
            print(json.dumps(status), flush=True)
            if args.once:
                if status["state"] != "uploaded" or not delivery.is_published():
                    raise SystemExit(1)
                return
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
