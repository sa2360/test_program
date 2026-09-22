"""Persistent image index and MQTT outbox for the two-board development server."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import uuid

from PIL import Image, UnidentifiedImageError

from app.protocol import VISION_RESULT_TOPIC
from app.vision_protocol import normalize_vision, unconfigured_result

ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
SCENES = {"rlc_series", "rlc_transient", "wheatstone_bridge"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024


class UploadError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class ImageStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "index.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS images (
                    image_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    device_id TEXT NOT NULL, digest TEXT NOT NULL,
                    metadata TEXT NOT NULL, result TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL, payload TEXT NOT NULL, sent INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL, topic TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def accept(self, request_id: str, device_id: str, scene: str, data: bytes) -> dict:
        if not ID_PATTERN.fullmatch(request_id):
            raise UploadError(400, "Invalid X-Request-ID (1-96 ASCII letters/digits/._-)")
        if device_id != "camera01":
            raise UploadError(400, "X-Device-ID must be camera01")
        if scene not in SCENES:
            raise UploadError(400, "Unknown experiment")
        if len(data) > MAX_IMAGE_BYTES:
            raise UploadError(413, "JPEG exceeds 2 MiB")
        if not (data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")):
            raise UploadError(400, "Invalid JPEG markers")
        try:
            with Image.open(BytesIO(data)) as picture:
                if picture.format != "JPEG" or picture.width * picture.height > 4_000_000:
                    raise UploadError(400, "JPEG dimensions exceed 4 megapixels")
                width, height = picture.size
                picture.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            if isinstance(exc, UploadError):
                raise
            raise UploadError(400, "JPEG cannot be decoded") from exc

        digest = hashlib.sha256(data).hexdigest()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM images WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                metadata = json.loads(existing["metadata"])
                if existing["digest"] != digest or metadata["scene"] != scene:
                    raise UploadError(409, "request_id was already used for different content")
                return {**metadata, "duplicate": True}
            image_id = f"img-{uuid.uuid4().hex[:16]}"
            path = self.root / f"{image_id}.jpg"
            metadata = {
                "image_id": image_id, "request_id": request_id, "device_id": device_id,
                "received_bytes": len(data), "status": "queued", "scene": scene,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "width": width, "height": height, "duplicate": False,
            }
            result = unconfigured_result(request_id, image_id, scene)
            encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
            # UUID filenames never incorporate caller-supplied paths.
            path.write_bytes(data)
            try:
                db.execute("INSERT INTO images VALUES (?, ?, ?, ?, ?, ?)",
                           (image_id, request_id, device_id, digest, json.dumps(metadata), encoded))
                db.execute("INSERT INTO outbox(topic,payload) VALUES (?,?)", (VISION_RESULT_TOPIC, encoded))
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return metadata

    def get(self, image_id: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT metadata,result FROM images WHERE image_id=?", (image_id,)).fetchone()
        if row is None:
            raise UploadError(404, "image_id not found")
        return {**json.loads(row["metadata"]), "vision": json.loads(row["result"])}

    def recent(self) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT metadata,result FROM images ORDER BY rowid DESC LIMIT 20").fetchall()
        return [{**json.loads(r["metadata"]), "vision": json.loads(r["result"])} for r in rows]

    def save_result(self, image_id: str, payload: dict) -> dict:
        result = normalize_vision(payload)
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM images WHERE image_id=?", (image_id,)).fetchone()
            if row is None:
                raise UploadError(404, "image_id not found")
            metadata = json.loads(row["metadata"])
            if (result["image_id"] != image_id or result["request_id"] != row["request_id"]
                    or result["scene"] != metadata["scene"]):
                raise UploadError(409, "image_id/request_id/scene mismatch")
            if encoded != row["result"]:
                db.execute("UPDATE images SET result=? WHERE image_id=?", (encoded, image_id))
                db.execute("INSERT INTO outbox(topic,payload) VALUES (?,?)", (VISION_RESULT_TOPIC, encoded))
        return result

    def enqueue(self, topic: str, payload: dict) -> int:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self.db() as db:
            cursor = db.execute("INSERT INTO outbox(topic,payload) VALUES (?,?)", (topic, encoded))
        return cursor.lastrowid

    def pending(self) -> list[dict]:
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM outbox WHERE sent=0 ORDER BY id LIMIT 20")]

    def mark_sent(self, message_id: int):
        with self.db() as db:
            db.execute("UPDATE outbox SET sent=1 WHERE id=?", (message_id,))

    def pending_count(self) -> int:
        with self.db() as db:
            return db.execute("SELECT COUNT(*) FROM outbox WHERE sent=0").fetchone()[0]

    def add_event(self, topic: str, payload: dict):
        with self.db() as db:
            db.execute("INSERT INTO events(received_at,topic,payload) VALUES (?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), topic, json.dumps(payload, ensure_ascii=False)))
            db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id)-1000 FROM events)")

    def events(self) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
