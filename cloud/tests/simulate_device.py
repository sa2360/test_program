import json
import time
from typing import Any

import paho.mqtt.client as mqtt

from app.protocol import (
    ASSISTANT_ANSWER_TOPIC,
    ASSISTANT_QUESTION_TOPIC,
    validate_message,
)


DEVICE_ID = "sensor01"
QUESTION_TOPIC = ASSISTANT_QUESTION_TOPIC
ANSWER_TOPIC = ASSISTANT_ANSWER_TOPIC


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    if reason_code.is_failure:
        raise RuntimeError(f"模拟设备连接失败：{reason_code}")
    client.subscribe(ANSWER_TOPIC, qos=1)
    question = {
        "schema": "physlab.assistant.question.v1",
        "device_id": DEVICE_ID,
        "request_id": "local-test-001",
        "ts": int(time.time() * 1000),
        "experiment": "rlc_series",
        "question": "什么是RLC串联谐振？",
    }
    validate_message("assistant.question.v1.schema.json", question)
    client.publish(
        QUESTION_TOPIC,
        json.dumps(question, ensure_ascii=False),
        qos=1,
    )
    print(f"模拟设备已发送：{question['question']}")


def on_message(
    client: mqtt.Client,
    userdata: dict[str, bool],
    message: mqtt.MQTTMessage,
) -> None:
    payload = json.loads(message.payload.decode("utf-8"))
    validate_message("assistant.answer.v1.schema.json", payload)
    print(f"模拟设备收到回答：{payload['answer']}")
    userdata["received"] = True
    client.disconnect()


def main() -> None:
    state = {"received": False}
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="simulated_esp32",
        userdata=state,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("127.0.0.1", 1883, keepalive=60)
    client.loop_forever()
    if not state["received"]:
        raise RuntimeError("未收到云端回答")


if __name__ == "__main__":
    main()
