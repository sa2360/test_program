"""A Day08-compatible HTTP receiver and persistent MQTT result delivery."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import sqlite3
from pathlib import Path
import threading
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import ValidationError
import paho.mqtt.client as mqtt

from app.config import Settings
from app.experiments import all_experiments
from app.image_store import ImageStore, MAX_IMAGE_BYTES, UploadError
from app.lab_store import LabError, LabStore
from app.llm_client import LlmAnswerService
from app.protocol import (ALARM_TOPIC, CAMERA_COMMAND_TOPIC, CAMERA_STATUS_TOPIC,
                          SENSOR_DATA_TOPIC, SENSOR_STATUS_TOPIC, unix_ms,
                          validate_message)
from app.vision_protocol import normalize_vision

logger = logging.getLogger(__name__)
EVENT_SCHEMAS = {
    CAMERA_STATUS_TOPIC: "camera.status.v1.schema.json",
    SENSOR_STATUS_TOPIC: "sensor.status.v1.schema.json",
    SENSOR_DATA_TOPIC: "sensor.data.v1.schema.json",
    ALARM_TOPIC: "alarm.v1.schema.json",
}
STATIC_DIR = Path(__file__).with_name("static")


class MqttBridge:
    def __init__(self, store: ImageStore, settings: Settings):
        self.store, self.settings = store, settings
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"image-server-{uuid.uuid4().hex[:8]}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(1, 10)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="image-outbox", daemon=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            client.subscribe([(topic, 1) for topic in EVENT_SCHEMAS])

    def on_message(self, client, userdata, message):
        try:
            if len(message.payload) > 16384:
                raise ValueError("MQTT payload too large")
            payload = json.loads(message.payload)
            validate_message(EVENT_SCHEMAS[message.topic], payload)
            self.store.add_event(message.topic, payload)
        except (ValueError, ValidationError, KeyError, UnicodeError, sqlite3.Error) as exc:
            logger.warning("Rejected event on %s: %s", message.topic, type(exc).__name__)

    def start(self):
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, 30)
        self.client.loop_start()
        self.thread.start()

    def run(self):
        while not self.stop_event.wait(0.25):
            if not self.client.is_connected():
                continue
            try:
                for item in self.store.pending():
                    if self.stop_event.is_set():
                        return
                    delivery = self.client.publish(item["topic"], item["payload"], qos=1, retain=False)
                    delivery.wait_for_publish(timeout=2)
                    if delivery.is_published():
                        self.store.mark_sent(item["id"])
                    else:
                        break
            except (OSError, RuntimeError, sqlite3.Error):
                logger.warning("MQTT delivery delayed; durable outbox will retry")

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)
        self.client.disconnect()
        self.client.loop_stop()


async def bounded_body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Request body too large")
        body.extend(chunk)
    return bytes(body)


async def json_body(request: Request, limit: int = 16384) -> dict:
    try:
        payload = json.loads((await bounded_body(request, limit)).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "Request body must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise HTTPException(422, "Request body must be a JSON object")
    return payload


def create_app(data_dir: Path | None = None, mqtt_enabled: bool = True,
               settings_override: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = settings_override or Settings.from_env()
        root = data_dir or Path(os.getenv("IMAGE_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data" / "images")))
        app.state.store = ImageStore(root)
        app.state.lab = LabStore(root)
        app.state.answers = LlmAnswerService(settings)
        app.state.bridge = MqttBridge(app.state.store, settings) if mqtt_enabled else None
        if app.state.bridge:
            app.state.bridge.start()
        try:
            yield
        finally:
            if app.state.bridge:
                await asyncio.to_thread(app.state.bridge.stop)

    app = FastAPI(title="PhysLab 双板图片与联调服务", lifespan=lifespan)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.exception_handler(UploadError)
    async def upload_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.exception_handler(LabError)
    async def lab_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    def student_page():
        return FileResponse(STATIC_DIR / "student.html", media_type="text/html")

    @app.get("/student", include_in_schema=False)
    def student_page_alias():
        return FileResponse(STATIC_DIR / "student.html", media_type="text/html")

    @app.get("/teacher", include_in_schema=False)
    def teacher_page():
        return FileResponse(STATIC_DIR / "teacher.html", media_type="text/html")

    @app.get("/health")
    def health():
        bridge = app.state.bridge
        return {"status": "ok", "mqtt_connected": bool(bridge and bridge.client.is_connected()),
                "pending_messages": app.state.store.pending_count(), "vision_backend": "unconfigured"}

    @app.post("/api/v1/images", status_code=201)
    async def upload(request: Request):
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/jpeg":
            raise HTTPException(415, "Content-Type must be image/jpeg")
        data = await bounded_body(request, MAX_IMAGE_BYTES)
        request_id = request.headers.get("x-request-id", "")
        experiment = await asyncio.to_thread(
            app.state.lab.upload_experiment, request_id, request.headers.get("x-experiment")
        )
        return await asyncio.to_thread(app.state.store.accept,
            request_id, request.headers.get("x-device-id", ""), experiment, data)

    @app.get("/api/v1/images")
    def recent():
        return app.state.store.recent()

    @app.get("/api/v1/images/{image_id}")
    def metadata(image_id: str):
        return app.state.store.get(image_id)

    @app.get("/api/v1/images/{image_id}/file")
    def image_file(image_id: str):
        record = app.state.store.get(image_id)
        return FileResponse(app.state.store.root / f"{record['image_id']}.jpg", media_type="image/jpeg")

    @app.post("/api/v1/images/{image_id}/result")
    async def result(image_id: str, request: Request):
        try:
            payload = json.loads(await bounded_body(request, 16384))
            # Explicit human review is the only backend currently available.
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            if payload.get("source") not in (None, "manual"):
                raise ValueError("This endpoint accepts manual review only")
            payload = normalize_vision(payload)
            payload["source"] = "manual"
            answer = await asyncio.to_thread(app.state.store.save_result, image_id, payload)
        except (ValidationError, ValueError, UnicodeError) as exc:
            if isinstance(exc, UploadError):
                raise
            raise HTTPException(422, "Invalid review result or inconsistent severity") from exc
        return {"status": "queued", "result": answer}

    @app.get("/api/v1/events")
    def events():
        return app.state.store.events()

    @app.get("/api/v1/experiments")
    def experiments():
        return {"experiments": all_experiments()}

    @app.post("/api/v1/qa")
    async def ask_assistant(request: Request):
        payload = await json_body(request)
        experiment, question = await asyncio.to_thread(
            app.state.lab.validate_question, payload.get("experiment"), payload.get("question")
        )
        answer = await asyncio.to_thread(app.state.answers.answer, question, experiment)
        await asyncio.to_thread(app.state.lab.record_qa, experiment, question, answer.source)
        return {"answer": answer.text, "source": answer.source, "error": answer.error}

    @app.post("/api/v1/teacher/questions", status_code=201)
    async def ask_teacher(request: Request):
        payload = await json_body(request)
        return await asyncio.to_thread(
            app.state.lab.add_teacher_question,
            payload.get("student_name"), payload.get("experiment"), payload.get("question"),
        )

    @app.get("/api/v1/teacher/questions")
    def teacher_questions():
        return app.state.lab.teacher_questions()

    @app.get("/api/v1/student/questions")
    def student_questions(student_name: str):
        return app.state.lab.student_questions(student_name)

    @app.post("/api/v1/teacher/questions/{question_id}/reply")
    async def reply_to_teacher_question(question_id: str, request: Request):
        payload = await json_body(request)
        return await asyncio.to_thread(app.state.lab.reply_to_question, question_id, payload.get("reply"))

    @app.post("/api/v1/datasets", status_code=201)
    async def create_dataset(request: Request):
        payload = await json_body(request)
        return await asyncio.to_thread(
            app.state.lab.create_dataset,
            payload.get("student_name"), payload.get("experiment"), payload.get("title"),
            payload.get("columns"),
        )

    @app.get("/api/v1/datasets")
    def datasets(student_name: str):
        return app.state.lab.list_datasets(student_name)

    @app.get("/api/v1/datasets/{dataset_id}")
    def dataset(dataset_id: str):
        return app.state.lab.dataset(dataset_id)

    @app.post("/api/v1/datasets/{dataset_id}/rows", status_code=201)
    async def add_dataset_row(dataset_id: str, request: Request):
        payload = await json_body(request)
        return await asyncio.to_thread(app.state.lab.add_dataset_row, dataset_id, payload.get("values"))

    @app.post("/api/v1/captures", status_code=202)
    async def request_capture(request: Request):
        payload = await json_body(request)
        request_id = f"capture-{uuid.uuid4().hex}"
        capture = await asyncio.to_thread(app.state.lab.record_capture, request_id, payload.get("experiment"))
        command = {
            "schema": "physlab.camera.cmd.v1", "request_id": request_id,
            "ts": unix_ms(), "action": "capture", "resolution": "VGA",
            "jpeg_quality": 15, "timeout_ms": 15000,
        }
        validate_message("camera.cmd.v1.schema.json", command)
        await asyncio.to_thread(app.state.store.enqueue, CAMERA_COMMAND_TOPIC, command)
        return {**capture, "status": "queued"}

    @app.get("/api/v1/captures/{request_id}")
    def capture(request_id: str):
        return app.state.lab.capture(request_id)

    @app.get("/api/v1/teacher/insights")
    def teacher_insights():
        return app.state.lab.insights()

    return app


app = create_app()
