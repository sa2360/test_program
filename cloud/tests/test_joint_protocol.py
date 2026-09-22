import unittest

from jsonschema import ValidationError

from app.protocol import validate_message
from app.vision_protocol import normalize_vision
from tools.mock_vision import build_payload


class JointProtocolTests(unittest.TestCase):
    def test_actual_a_day08_status_passes(self):
        validate_message("camera.status.v1.schema.json", {
            "schema": "physlab.camera.status.v1", "device_id": "camera01",
            "request_id": "req-day08-001", "state": "uploaded",
            "image_id": "img-88b75b24c5dc", "bytes": 12345,
            "http_status": 201, "heap": 265176, "psram": 8306911, "error": None,
        })

    def test_a_upload_failure_allows_negative_httpclient_error(self):
        validate_message("camera.status.v1.schema.json", {
            "schema": "physlab.camera.status.v1", "device_id": "camera01",
            "request_id": "req-001", "state": "upload_failed", "image_id": "",
            "bytes": 0, "http_status": -1, "heap": 1000, "psram": 1000,
            "error": "http_upload_failed",
        })

    def test_uploaded_status_cannot_claim_success_without_image(self):
        with self.assertRaises(ValidationError):
            validate_message("camera.status.v1.schema.json", {
                "schema": "physlab.camera.status.v1", "device_id": "camera01",
                "request_id": "req-001", "state": "uploaded", "image_id": "",
                "bytes": 0, "http_status": 500, "error": "upload_failed",
            })

    def test_day08_command_without_timestamp_passes(self):
        validate_message("camera.cmd.v1.schema.json", {
            "schema": "physlab.camera.cmd.v1", "request_id": "req-day08-001",
            "action": "capture", "resolution": "VGA", "jpeg_quality": 15, "timeout_ms": 15000,
        })

    def test_legacy_b_vision_is_preserved(self):
        old = build_payload("inductor_missing", "req-legacy")
        new = normalize_vision(old)
        self.assertEqual(new["request_id"], old["request_id"])
        self.assertEqual(new["result"], "warning")
        self.assertEqual(new["warnings"][0]["code"], old["warning"])

    def test_extended_sensor_measurement_uses_volts_and_calibration_state(self):
        validate_message("sensor.data.v1.schema.json", {
            "schema": "physlab.sensor.data.v1", "device_id": "sensor01",
            "experiment": "rlc_series", "ts": 0, "voltage_v": 1.65,
            "temperature_c": None, "quality": "degraded", "channel": "A0",
            "raw": 8800, "range_v": 6.144, "calibrated": False, "request_id": "sample-001",
        })
