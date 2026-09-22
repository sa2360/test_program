"""Isolated real MQTT/HTTP integration test. No hardware or paid API required."""
import asyncio
import json
import logging
from pathlib import Path
import socket
import tempfile
import threading
import uuid

from tools.run_broker import ExclusiveBroker as Broker
import httpx
import paho.mqtt.client as mqtt
import uvicorn

from app.config import Settings
from app.image_server import create_app
from app.protocol import CAMERA_COMMAND_TOPIC, CAMERA_STATUS_TOPIC, VISION_RESULT_TOPIC, validate_message
from app.vision_protocol import normalize_vision


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def wait_for(predicate, label, timeout=8):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError(f"Timed out: {label}")
        await asyncio.sleep(0.05)


async def main():
    mqtt_port, http_port = free_port(), free_port()
    while http_port == mqtt_port:
        http_port = free_port()
    broker = Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{mqtt_port}"}},
                     "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}})
    request_id = "integration-" + uuid.uuid4().hex[:12]
    fixture = (Path(__file__).resolve().parents[2] / "handoff" / "a_day08" / "ESP32 Project" /
               "evidence" / "day08" / "uploaded_image_req-day08-001.jpg")
    image_bytes = fixture.read_bytes()
    messages = []
    capture_received, subscribed = threading.Event(), threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="joint-integration-observer")

    def received(client, userdata, message):
        payload = json.loads(message.payload)
        messages.append((message.topic, payload))
        if message.topic == CAMERA_COMMAND_TOPIC:
            capture_received.set()

    client.on_connect = lambda c, u, f, r, p: c.subscribe("physlab/#", qos=1) if not r.is_failure else None
    client.on_subscribe = lambda c, u, m, r, p: subscribed.set()
    client.on_message = received
    server = None
    server_task = None
    await broker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="physlab-joint-") as temp:
            settings = Settings("127.0.0.1", mqtt_port, "sensor01", "INFO", llm_enabled=False)
            app = create_app(Path(temp), settings_override=settings)
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=http_port, log_level="error"))
            server_task = asyncio.create_task(server.serve())
            try:
                await wait_for(lambda: server.started, "HTTP server start")
                client.connect("127.0.0.1", mqtt_port)
                client.loop_start()
                await wait_for(subscribed.is_set, "MQTT subscriptions")
                await wait_for(lambda: app.state.bridge.client.is_connected(), "image bridge MQTT")
                command = {"schema": "physlab.camera.cmd.v1", "request_id": request_id,
                           "action": "capture", "resolution": "VGA", "jpeg_quality": 15, "timeout_ms": 15000}
                validate_message("camera.cmd.v1.schema.json", command)
                client.publish(CAMERA_COMMAND_TOPIC, json.dumps(command), qos=1)
                await wait_for(capture_received.is_set, "camera command")
                print("PASS 1: camera command through real MQTT", flush=True)

                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{http_port}", trust_env=False) as http:
                    headers = {"Content-Type": "image/jpeg", "X-Device-ID": "camera01", "X-Request-ID": request_id}
                    response = await http.post("/api/v1/images", headers=headers, content=image_bytes)
                    assert response.status_code == 201, response.text
                    metadata = response.json()
                    assert metadata["received_bytes"] == len(image_bytes)
                    assert metadata["request_id"] == request_id
                    print(f"PASS 2: A Day08 JPEG uploaded and decoded ({len(image_bytes)} bytes)", flush=True)

                    status = {"schema": "physlab.camera.status.v1", "device_id": "camera01",
                              "request_id": request_id, "state": "uploaded", "image_id": metadata["image_id"],
                              "bytes": len(image_bytes), "http_status": 201, "heap": 265176,
                              "psram": 8306911, "error": None}
                    client.publish(CAMERA_STATUS_TOPIC, json.dumps(status), qos=1)
                    await wait_for(lambda: any(t == VISION_RESULT_TOPIC for t, _ in messages), "initial vision result")
                    initial = normalize_vision(next(p for t, p in messages if t == VISION_RESULT_TOPIC))
                    assert initial["request_id"] == request_id and initial["image_id"] == metadata["image_id"]
                    assert initial["result"] == "unknown" and initial["source"] == "unconfigured"
                    await wait_for(lambda: any(e["topic"] == CAMERA_STATUS_TOPIC for e in app.state.store.events()), "camera status log")
                    print("PASS 3: same request/image ID reaches vision MQTT; A status recorded", flush=True)

                    duplicate = await http.post("/api/v1/images", headers=headers, content=image_bytes)
                    assert duplicate.json()["image_id"] == metadata["image_id"]
                    assert duplicate.json()["duplicate"]
                    print("PASS 4: duplicate upload keeps one image and one initial result", flush=True)

                    # Simulate disconnection of the publishing component. Persist a review,
                    # then recreate the bridge to prove queued results survive reconnect.
                    await asyncio.to_thread(app.state.bridge.stop)
                    payload = {**initial, "result": "danger", "source": "manual",
                               "warnings": [{"level": "danger", "code": "POWER_RISK", "message": "Integration test only"}],
                               "suggestion": "Manual integration test; no real circuit assessment."}
                    review = await http.post(f"/api/v1/images/{metadata['image_id']}/result", json=payload)
                    assert review.status_code == 200, review.text
                    assert app.state.store.pending()
                    from app.image_server import MqttBridge
                    app.state.bridge = MqttBridge(app.state.store, settings)
                    app.state.bridge.start()
                    await wait_for(lambda: any(t == VISION_RESULT_TOPIC and p.get("result") == "danger" for t, p in messages), "queued manual result")
                    await wait_for(lambda: not app.state.store.pending(), "outbox acknowledgment")
                    print("PASS 5: disconnected result persisted, reconnected and acknowledged", flush=True)
            finally:
                client.disconnect()
                client.loop_stop()
                server.should_exit = True
                await asyncio.wait_for(server_task, timeout=10)
                assert not app.state.bridge.thread.is_alive()
    finally:
        await broker.shutdown()
    print("PASS 6: HTTP, MQTT and worker stopped cleanly", flush=True)
    print("JOINT LOOP PASSED (simulated camera; no physical-board or model accuracy claim)", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(main())
