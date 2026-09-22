import unittest

from jsonschema.exceptions import ValidationError

from app.protocol import validate_message


class ProtocolSchemaTests(unittest.TestCase):
    def test_v1_examples_are_valid(self) -> None:
        examples = {
            "assistant.question.v1.schema.json": {
                "schema": "physlab.assistant.question.v1",
                "device_id": "sensor01",
                "request_id": "req-001",
                "experiment": "rlc_series",
                "ts": 1,
                "question": "什么是谐振？",
            },
            "assistant.answer.v1.schema.json": {
                "schema": "physlab.assistant.answer.v1",
                "device_id": "sensor01",
                "request_id": "req-001",
                "experiment": "rlc_series",
                "ts": 2,
                "answer": "感抗等于容抗时发生谐振。",
                "severity": "info",
                "source": "agnes",
                "error": None,
            },
            "sensor.status.v1.schema.json": {
                "schema": "physlab.sensor.status.v1",
                "device_id": "sensor01",
                "ts": 2,
                "online": True,
                "rssi": -45,
                "uptime_ms": 1234,
                "heap_bytes": 180000,
                "fw": "sensor01-fw-0.2.0",
                "clock_synced": True,
                "error": None,
            },
            "sensor.data.v1.schema.json": {
                "schema": "physlab.sensor.data.v1",
                "device_id": "sensor01",
                "experiment": "wheatstone_bridge",
                "ts": 3,
                "voltage_v": 1.65,
                "temperature_c": None,
                "quality": "ok",
            },
            "sensor.cmd.v1.schema.json": {
                "schema": "physlab.sensor.cmd.v1",
                "request_id": "req-002",
                "ts": 4,
                "action": "sample_now",
                "params": {},
            },
            "camera.cmd.v1.schema.json": {
                "schema": "physlab.camera.cmd.v1",
                "request_id": "req-003",
                "ts": 5,
                "action": "capture",
                "resolution": "VGA",
                "jpeg_quality": 15,
                "timeout_ms": 15000,
            },
            "camera.status.v1.schema.json": {
                "schema": "physlab.camera.status.v1",
                "device_id": "camera01",
                "request_id": "req-003",
                "ts": 6,
                "state": "uploaded",
                "image_id": "img-003",
                "bytes": 86420,
                "http_status": 201,
                "heap_bytes": 182300,
                "error": None,
            },
            "vision.result.v1.schema.json": {
                "schema": "physlab.vision.v1",
                "request_id": "req-003",
                "image_id": "img-003",
                "experiment": "rlc_series",
                "ts": 7,
                "objects": [{"name": "resistor", "confidence": 0.92}],
                "warning": "inductor_missing",
                "message": "未检测到电感，请检查器材和接线",
                "processing_ms": 380,
            },
            "alarm.v1.schema.json": {
                "schema": "physlab.alarm.v1",
                "request_id": "req-003",
                "source": "sensor01",
                "code": "inductor_missing",
                "level": "warning",
                "message": "未检测到电感，请检查器材和接线",
                "ts": 8,
            },
        }

        for filename, payload in examples.items():
            with self.subTest(filename=filename):
                validate_message(filename, payload)

    def test_missing_request_id_is_rejected(self) -> None:
        payload = {
            "schema": "physlab.vision.v1",
            "image_id": "img-003",
            "experiment": "rlc_series",
            "ts": 7,
            "objects": [],
            "warning": None,
            "message": "",
            "processing_ms": 10,
        }
        with self.assertRaises(ValidationError):
            validate_message("vision.result.v1.schema.json", payload)


if __name__ == "__main__":
    unittest.main()
