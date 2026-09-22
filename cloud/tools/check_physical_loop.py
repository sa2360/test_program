"""Verify real camera uploads and sensor alarms against a running lab server.

This sends capture commands to camera01. Do not run a camera simulator alongside it.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import uuid

import httpx
from jsonschema import ValidationError
import paho.mqtt.client as mqtt

from app.protocol import ALARM_TOPIC, CAMERA_STATUS_TOPIC, VISION_RESULT_TOPIC, validate_message
from app.vision_protocol import normalize_vision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--camera-only", action="store_true", help="Check A/HTTP/MQTT only; does not certify B alarms")
    parser.add_argument("--timeout", type=float, default=35)
    parser.add_argument("--output", type=Path, default=Path("data/acceptance/physical-loop.json"))
    args = parser.parse_args()
    if not 1 <= args.count <= 100 or args.timeout <= 0:
        parser.error("count must be 1-100 and timeout must be positive")
    ready = threading.Event()
    lock = threading.Lock()
    messages = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"physical-check-{uuid.uuid4().hex[:8]}")

    def connected(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe([(CAMERA_STATUS_TOPIC, 1), (VISION_RESULT_TOPIC, 1), (ALARM_TOPIC, 1)])

    def subscribed(client, userdata, mid, reasons, properties):
        if all(not reason.is_failure for reason in reasons):
            ready.set()

    def received(client, userdata, message):
        if message.retain:
            return
        try:
            payload = json.loads(message.payload)
            if message.topic == VISION_RESULT_TOPIC:
                normalize_vision(payload)
            else:
                validate_message("camera.status.v1.schema.json" if message.topic == CAMERA_STATUS_TOPIC
                                 else "alarm.v1.schema.json", payload)
            with lock:
                messages.append({"topic": message.topic, "payload": payload})
        except (ValueError, TypeError, KeyError, ValidationError):
            return

    client.on_connect, client.on_subscribe, client.on_message = connected, subscribed, received
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "runs": [], "passed": False,
              "scope": "camera_only" if args.camera_only else "camera_and_sensor",
              "mode": "physical devices required; no simulator is started by this tool"}
    try:
        client.connect(args.host, args.port, 30)
        client.loop_start()
        if not ready.wait(5):
            raise RuntimeError("MQTT subscription failed")
        with httpx.Client(base_url=args.url, timeout=10) as http:
            health = http.get("/health")
            health.raise_for_status()
            if not health.json()["mqtt_connected"]:
                raise RuntimeError("Image service is not connected to MQTT")
            for index in range(args.count):
                experiment = ("rlc_series", "rlc_transient", "wheatstone_bridge")[index % 3]
                start = time.monotonic()
                response = http.post("/api/v1/captures", json={"experiment": experiment})
                response.raise_for_status()
                request_id = response.json()["request_id"]
                run = {"request_id": request_id, "experiment": experiment, "passed": False}
                report["runs"].append(run)
                while time.monotonic() - start < args.timeout:
                    response = http.get(f"/api/v1/captures/{request_id}")
                    response.raise_for_status()
                    capture = response.json()
                    with lock:
                        matched = [item for item in messages if item["payload"].get("request_id") == request_id]
                    run["messages"] = matched
                    image = capture.get("image")
                    if image:
                        run["image"] = image
                        if image["scene"] != experiment:
                            raise RuntimeError(f"Wrong image scene for {request_id}")
                        image_id = image["image_id"]
                        uploaded = any(m["topic"] == CAMERA_STATUS_TOPIC and m["payload"].get("state") == "uploaded"
                                       and m["payload"].get("image_id") == image_id for m in matched)
                        vision = any(m["topic"] == VISION_RESULT_TOPIC and m["payload"].get("image_id") == image_id
                                     and m["payload"].get("result") == "unknown" for m in matched)
                        alarm = any(m["topic"] == ALARM_TOPIC and m["payload"].get("source") == "sensor01"
                                    and m["payload"].get("code") == "vision_unknown" for m in matched)
                        run["checks"] = {"camera_uploaded": uploaded, "vision_received": vision, "sensor_alarm": alarm}
                        if uploaded and vision and (alarm or args.camera_only):
                            run.update(passed=True, elapsed_seconds=round(time.monotonic() - start, 3))
                            print(f"PASS {index + 1}/{args.count}: {request_id} {image_id} {experiment}", flush=True)
                            break
                    time.sleep(0.2)
                if not run["passed"]:
                    raise RuntimeError(f"Missing upload/result/sensor alarm for {request_id}")
                time.sleep(0.5)
        report["passed"] = True
        print(f"PHYSICAL CHECK PASSED: {report['scope']} (vision remains unconfigured)", flush=True)
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        client.disconnect()
        client.loop_stop()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
