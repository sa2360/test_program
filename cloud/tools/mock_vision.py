import argparse
import json
import os
import time
import uuid

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from app.protocol import VISION_RESULT_TOPIC, validate_message


MESSAGES = {
    "none": "器材检测正常",
    "inductor_missing": "未检测到电感，请检查器材和接线",
    "vision_timeout": "视觉识别超时，本地采样应继续运行",
}


def build_payload(warning: str, request_id: str) -> dict:
    return {
        "schema": "physlab.vision.v1",
        "request_id": request_id,
        "image_id": f"mock-{request_id}",
        "experiment": "rlc_series",
        "ts": int(time.time() * 1000),
        "objects": (
            [{"name": "resistor", "confidence": 0.95}]
            if warning == "none"
            else []
        ),
        "warning": None if warning == "none" else warning,
        "message": MESSAGES[warning],
        "processing_ms": 25,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="发布模拟视觉结果")
    parser.add_argument(
        "--warning",
        choices=sorted(MESSAGES),
        default="inductor_missing",
    )
    parser.add_argument("--request-id", default=f"mock-{uuid.uuid4().hex[:10]}")
    args = parser.parse_args()

    load_dotenv()
    payload = build_payload(args.warning, args.request_id)
    validate_message("vision.result.v1.schema.json", payload)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"mock-vision-{uuid.uuid4().hex[:8]}",
    )
    client.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")))
    client.loop_start()
    result = client.publish(
        VISION_RESULT_TOPIC,
        json.dumps(payload, ensure_ascii=False),
        qos=1,
    )
    result.wait_for_publish(timeout=5)
    client.loop_stop()
    client.disconnect()
    print(f"已发布模拟视觉结果：{args.warning}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
