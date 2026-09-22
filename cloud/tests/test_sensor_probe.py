import unittest

from app.protocol import ALARM_TOPIC, SENSOR_DATA_TOPIC
from tools.check_sensor import select_response


class SensorProbeTests(unittest.TestCase):
    def sample(self):
        return {"schema": "physlab.sensor.data.v1", "device_id": "sensor01", "request_id": "current",
                "experiment": "rlc_series", "ts": 0, "voltage_v": 0.001, "temperature_c": None,
                "quality": "degraded", "channel": "A0", "raw": 5, "calibrated": False, "range_v": 6.144}

    def test_uncalibrated_sample_is_preserved_not_promoted(self):
        result = select_response(SENSOR_DATA_TOPIC, self.sample(), "current")
        self.assertEqual(result["kind"], "sample")
        self.assertFalse(result["payload"]["calibrated"])
        self.assertEqual(result["payload"]["quality"], "degraded")

    def test_other_request_cannot_satisfy_sample(self):
        self.assertIsNone(select_response(SENSOR_DATA_TOPIC, self.sample(), "different"))

    def test_missing_sensor_alarm_is_failure_not_zero_volts(self):
        alarm = {"schema": "physlab.alarm.v1", "source": "sensor01", "request_id": "current",
                 "ts": 0, "code": "sensor_read_error", "level": "warning", "message": "ADS1115 is not connected."}
        self.assertEqual(select_response(ALARM_TOPIC, alarm, "current")["kind"], "alarm")
        self.assertIsNone(select_response(ALARM_TOPIC, {**alarm, "source": "camera01"}, "current"))

    def test_invalid_or_nonfinite_measurement_is_rejected(self):
        for value in (None, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                select_response(SENSOR_DATA_TOPIC, {**self.sample(), "voltage_v": value}, "current")
        with self.assertRaises(ValueError):
            select_response(SENSOR_DATA_TOPIC, {**self.sample(), "quality": "invalid"}, "current")
