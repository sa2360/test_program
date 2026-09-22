"""Human object annotations, independent of live vision/alarm results."""
from datetime import datetime, timezone
from io import BytesIO
import json
import math
import zipfile

from app.image_store import UploadError


LABELS = {"resistor": "电阻", "capacitor": "电容", "inductor": "电感", "oscilloscope": "示波器",
          "signal_generator": "信号发生器", "power_supply": "电源", "multimeter": "万用表",
          "breadboard": "面包板", "bridge_box": "电桥箱", "wire": "导线",
          "esp32": "ESP32 开发板", "ads1115": "ADS1115 模块"}


class AnnotationStore:
    def __init__(self, images):
        self.images = images
        with images.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS annotations (
                image_id TEXT PRIMARY KEY REFERENCES images(image_id),
                revision INTEGER NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)""")

    def get(self, image_id):
        image = self.images.get(image_id)
        with self.images.db() as db:
            row = db.execute("SELECT * FROM annotations WHERE image_id=?", (image_id,)).fetchone()
        return {"image": image, "annotation": json.loads(row["payload"]) if row else None,
                "revision": row["revision"] if row else 0, "updated_at": row["updated_at"] if row else None}

    def listing(self, before=0, limit=30):
        with self.images.db() as db:
            rows = db.execute("""SELECT i.rowid AS cursor,i.metadata,a.payload,a.revision FROM images i
                LEFT JOIN annotations a ON a.image_id=i.image_id
                WHERE (?=0 OR i.rowid<?) ORDER BY i.rowid DESC LIMIT ?""", (before, before, limit)).fetchall()
        return [{"cursor": r["cursor"], "image": json.loads(r["metadata"]),
                 "annotation": json.loads(r["payload"]) if r["payload"] else None,
                 "revision": r["revision"] or 0} for r in rows]

    def save(self, image_id, payload):
        self.images.get(image_id)
        if set(payload) != {"revision", "reviewer", "group_id", "status", "quality", "negative", "notes", "boxes"}:
            raise UploadError(422, "Annotation fields are missing or unknown")
        revision = payload["revision"]
        if type(revision) is not int or revision < 0:
            raise UploadError(422, "Invalid revision")
        clean = {}
        for field, maximum in (("reviewer", 60), ("group_id", 80), ("notes", 1000)):
            value = payload[field]
            if not isinstance(value, str) or len(value.strip()) > maximum:
                raise UploadError(422, f"Invalid {field}")
            clean[field] = value.strip()
        status, quality = payload["status"], payload["quality"]
        if status not in ("draft", "ready", "excluded") or quality not in ("usable", "blurred", "occluded", "not_experiment"):
            raise UploadError(422, "Invalid annotation status/quality")
        if type(payload["negative"]) is not bool or not isinstance(payload["boxes"], list) or len(payload["boxes"]) > 100:
            raise UploadError(422, "Invalid negative/boxes")
        boxes = []
        for box in payload["boxes"]:
            if (not isinstance(box, dict) or set(box) != {"label", "x", "y", "w", "h"}
                    or not isinstance(box["label"], str) or box["label"] not in LABELS):
                raise UploadError(422, "Invalid object label or box fields")
            for key in ("x", "y", "w", "h"):
                if type(box[key]) not in (int, float) or not math.isfinite(box[key]):
                    raise UploadError(422, "Box coordinates must be finite numbers")
            if (box["x"] < 0 or box["y"] < 0 or box["w"] <= 0 or box["h"] <= 0
                    or box["x"] + box["w"] > 1.000001 or box["y"] + box["h"] > 1.000001):
                raise UploadError(422, "Box lies outside the image")
            boxes.append(dict(box))
        if payload["negative"] and boxes:
            raise UploadError(422, "Negative images cannot contain object boxes")
        if status == "ready" and (not clean["reviewer"] or not clean["group_id"] or quality != "usable"
                                  or (not boxes and not payload["negative"])):
            raise UploadError(422, "Ready images need reviewer, group, usable quality and boxes or explicit negative confirmation")
        clean.update(status=status, quality=quality, negative=payload["negative"], boxes=boxes, source="human")
        now = datetime.now(timezone.utc).isoformat()
        with self.images.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT revision FROM annotations WHERE image_id=?", (image_id,)).fetchone()
            if revision != (current["revision"] if current else 0):
                raise UploadError(409, "Annotation changed elsewhere; reload before saving")
            db.execute("INSERT OR REPLACE INTO annotations VALUES (?,?,?,?)",
                       (image_id, revision + 1, json.dumps(clean, ensure_ascii=False), now))
        return {"annotation": clean, "revision": revision + 1, "updated_at": now}

    def export(self):
        with self.images.db() as db:
            rows = db.execute("""SELECT i.image_id,i.metadata,a.payload,a.revision,a.updated_at
                FROM annotations a JOIN images i ON i.image_id=a.image_id ORDER BY i.rowid""").fetchall()
        records = []
        total = 0
        for row in rows:
            annotation = json.loads(row["payload"])
            if annotation["status"] != "ready":
                continue
            metadata = json.loads(row["metadata"])
            path = self.images.root / f"{row['image_id']}.jpg"
            total += path.stat().st_size
            if total > 100 * 1024 * 1024:
                raise UploadError(413, "Export exceeds 100 MiB; use smaller dataset batches")
            records.append({"image": metadata, "annotation": annotation, "revision": row["revision"],
                            "updated_at": row["updated_at"], "file": f"images/{row['image_id']}.jpg"})
        if not records:
            raise UploadError(409, "No ready human annotations to export")
        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = {"schema": "physlab.annotations.v1", "coordinates": "normalized top-left x,y,width,height",
                        "labels": LABELS, "images": records,
                        "split_note": "Keep each group_id in one split; nearby photos of the same setup must not leak across train/test."}
            archive.writestr("annotations.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for record in records:
                archive.write(self.images.root / f"{record['image']['image_id']}.jpg", record["file"])
        return output.getvalue()
