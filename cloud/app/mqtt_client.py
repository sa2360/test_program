import json
import time
from typing import Any

import paho.mqtt.client as mqtt
from jsonschema.exceptions import ValidationError

from app.config import Settings
from app.llm_client import AnswerResult, LlmAnswerService
from app.protocol import (
    ASSISTANT_ANSWER_TOPIC,
    ASSISTANT_QUESTION_TOPIC,
    unix_ms,
    validate_message,
)


def make_answer(
    payload: dict[str, Any],
    result: AnswerResult,
) -> dict[str, Any]:
    return {
        "schema": "physlab.assistant.answer.v1",
        "device_id": payload["device_id"],
        "request_id": payload["request_id"],
        "experiment": payload.get("experiment", "general"),
        "ts": unix_ms(),
        "answer": result.text,
        "severity": "info" if result.error is None else "warning",
        "source": result.source,
        "error": result.error,
    }


class CloudMqttService:
    def __init__(
        self,
        settings: Settings,
        answer_service: LlmAnswerService | None = None,
    ) -> None:
        self.settings = settings
        self.answer_service = answer_service or LlmAnswerService(settings)
        self.question_topic = ASSISTANT_QUESTION_TOPIC
        self.answer_topic = ASSISTANT_ANSWER_TOPIC
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="cloud_service_b",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            print(f"MQTT连接失败：{reason_code}")
            return
        client.subscribe(self.question_topic, qos=1)
        print(f"MQTT连接成功，已订阅：{self.question_topic}")

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            validate_message("assistant.question.v1.schema.json", payload)
            question = payload["question"]
            experiment = payload.get("experiment", "general")
            result = self.answer_service.answer(question, experiment)
            answer = make_answer(payload, result)
            validate_message("assistant.answer.v1.schema.json", answer)
            client.publish(
                self.answer_topic,
                json.dumps(answer, ensure_ascii=False),
                qos=1,
            )
            print(f"收到问题：{question}")
            print(f"已发布回答：{answer['answer']}")
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValidationError,
        ) as exc:
            print(f"消息处理失败：{exc}")

    def run_forever(self) -> None:
        while True:
            print(
                f"正在连接MQTT：{self.settings.mqtt_host}:"
                f"{self.settings.mqtt_port}"
            )
            try:
                self.client.connect(
                    self.settings.mqtt_host,
                    self.settings.mqtt_port,
                    keepalive=60,
                )
                self.client.loop_forever()
            except (OSError, mqtt.MQTTException) as exc:
                print(f"MQTT暂时不可用：{exc}，2秒后重试")
                time.sleep(2)
