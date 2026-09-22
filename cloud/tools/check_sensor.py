"""Request correlated ADS1115 samples; save measurements or explicit device failures."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import statistics
import threading
import time
import uuid

from jsonschema import ValidationError
import paho.mqtt.client as mqtt

from app.config import Settings
from app.protocol import ALARM_TOPIC, SENSOR_COMMAND_TOPIC, SENSOR_DATA_TOPIC, unix_ms, validate_message


def select_response(topic, payload, request_id):
    if not isinstance(payload, dict) or payload.get("request_id") != request_id:
        return None
    if topic == ALARM_TOPIC:
        validate_message("alarm.v1.schema.json", payload)
        return {"kind": "alarm", "payload": payload} if payload["source"] == "sensor01" else None
    if topic != SENSOR_DATA_TOPIC:
        return None
    validate_message("sensor.data.v1.schema.json", payload)
    voltage = payload["voltage_v"]
    if (payload.get("channel") != "A0" or "raw" not in payload
            or voltage is None or not math.isfinite(voltage) or payload["quality"] == "invalid"):
        raise ValueError("Missing or invalid A0 raw measurement")
    return {"kind": "sample", "payload": payload}


def main():
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=settings.mqtt_host)
    parser.add_argument("--port", type=int, default=settings.mqtt_port)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--reference-voltage", type=float)
    parser.add_argument("--max-error", type=float, help="User-defined absolute error limit in volts")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.count <= 1000 or not math.isfinite(args.timeout) or not 0 < args.timeout <= 60:
        parser.error("count must be 1-1000; timeout must be 0-60 seconds")
    if (args.reference_voltage is None) != (args.max_error is None):
        parser.error("reference-voltage and max-error must be supplied together")
    if args.reference_voltage is not None and (
        not math.isfinite(args.reference_voltage) or not 0 <= args.reference_voltage <= 3.3
        or not math.isfinite(args.max_error) or args.max_error <= 0
    ):
        parser.error("reference must be 0-3.3 V for this wiring; max-error must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path(f"data/acceptance/sensor-{stamp}-{uuid.uuid4().hex[:6]}.json")
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "passed": False,
              "requested_samples": args.count, "samples": [], "failures": [],
              "reference_voltage": args.reference_voltage, "max_error_v": args.max_error,
              "calibration_applied": False}
    ready = threading.Event()
    responses = queue.Queue()
    active = {"request_id": None}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-check-{uuid.uuid4().hex[:8]}")

    def connected(c, userdata, flags, reason, properties):
        if not reason.is_failure:
            c.subscribe([(SENSOR_DATA_TOPIC, 1), (ALARM_TOPIC, 1)])

    def received(c, userdata, message):
        if message.retain:
            return
        try:
            response = select_response(message.topic, json.loads(message.payload), active["request_id"])
            if response:
                responses.put(response)
        except (ValueError, TypeError, ValidationError):
            return

    client.on_connect, client.on_message = connected, received
    client.on_subscribe = lambda c, u, m, reasons, p: ready.set() if all(not r.is_failure for r in reasons) else None
    try:
        client.connect(args.host, args.port, 30)
        client.loop_start()
        if not ready.wait(5):
            raise RuntimeError("MQTT subscription failed")
        for index in range(args.count):
            request_id = f"sample-check-{uuid.uuid4().hex}"
            active["request_id"] = request_id
            command = {"schema": "physlab.sensor.cmd.v1", "request_id": request_id,
                       "ts": unix_ms(), "action": "sample_now", "params": {}}
            validate_message("sensor.cmd.v1.schema.json", command)
            delivery = client.publish(SENSOR_COMMAND_TOPIC, json.dumps(command), qos=1, retain=False)
            delivery.wait_for_publish(5)
            if not delivery.is_published():
                raise RuntimeError("Broker did not acknowledge sample command")
            # Late/duplicate messages from earlier requests cannot satisfy this sample.
            deadline = time.monotonic() + args.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                response = responses.get(timeout=remaining)
                if response["payload"]["request_id"] == request_id:
                    break
            if response["kind"] == "alarm":
                report["failures"].append(response["payload"])
                raise RuntimeError(f"Device reported {response['payload']['code']}: {response['payload']['message']}")
            report["samples"].append(response["payload"])
            print(f"SAMPLE {index + 1}/{args.count}: raw={response['payload']['raw']} voltage_v={response['payload']['voltage_v']}", flush=True)
        values = [item["voltage_v"] for item in report["samples"]]
        report["summary"] = {"mean_v": statistics.mean(values), "min_v": min(values), "max_v": max(values),
                             "stdev_v": statistics.stdev(values) if len(values) > 1 else None}
        if args.reference_voltage is not None:
            errors = [abs(v - args.reference_voltage) for v in values]
            report["summary"]["max_abs_error_v"] = max(errors)
            if max(errors) > args.max_error:
                raise RuntimeError("Measured error exceeds the specified limit")
        report["passed"] = True
        print("SAMPLING PASSED; this does not apply or certify calibration", flush=True)
    except (OSError, RuntimeError, queue.Empty) as exc:
        report["error"] = str(exc) or "Timed out waiting for the matching sensor response"
        print(report["error"], flush=True)
    finally:
        client.disconnect()
        client.loop_stop()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Evidence: {output}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
