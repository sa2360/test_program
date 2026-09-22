import argparse
import json
import os
import uuid

import paho.mqtt.client as mqtt
from jsonschema import ValidationError
from dotenv import load_dotenv

from app.protocol import (
    ALARM_TOPIC,
    ASSISTANT_ANSWER_TOPIC,
    CAMERA_STATUS_TOPIC,
    SENSOR_DATA_TOPIC,
    VISION_RESULT_TOPIC,
    validate_message,
)
from app.vision_protocol import normalize_vision


TARGETS = {
    "vision": (VISION_RESULT_TOPIC, "vision.result.v1.schema.json"),
    "alarm": (ALARM_TOPIC, "alarm.v1.schema.json"),
    "answer": (ASSISTANT_ANSWER_TOPIC, "assistant.answer.v1.schema.json"),
    "camera": (CAMERA_STATUS_TOPIC, "camera.status.v1.schema.json"),
    "sensor": (SENSOR_DATA_TOPIC, "sensor.data.v1.schema.json"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="接收并校验一条 MQTT V1 消息")
    parser.add_argument("target", choices=sorted(TARGETS))
    args = parser.parse_args()

    load_dotenv()
    topic, schema = TARGETS[args.target]
    state = {"received": False}

    def on_connect(client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            raise RuntimeError(f"MQTT 连接失败：{reason_code}")
        client.subscribe(topic, qos=1)

    def on_message(client, userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if args.target == "vision":
                payload = normalize_vision(payload)
            else:
                validate_message(schema, payload)
        except (ValueError, ValidationError, UnicodeError):
            print(f"忽略未通过协议校验的消息：{message.topic}")
            return
        print(f"已收到并通过 Schema 校验：{message.topic}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        state["received"] = True
        client.disconnect()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"monitor-once-{uuid.uuid4().hex[:8]}",
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(
        os.getenv("MQTT_HOST", "127.0.0.1"),
        int(os.getenv("MQTT_PORT", "1883")),
    )
    client.loop_forever()
    if not state["received"]:
        raise RuntimeError("监听结束前未收到消息")


if __name__ == "__main__":
    main()
