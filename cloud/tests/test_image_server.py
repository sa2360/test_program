from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from PIL import Image

from app.image_server import create_app
from app.image_store import ImageStore, MAX_IMAGE_BYTES


def jpeg_bytes(color="white"):
    stream = BytesIO()
    Image.new("RGB", (32, 24), color).save(stream, format="JPEG")
    return stream.getvalue()


class ImageServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root, mqtt_enabled=False)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = {"Content-Type": "image/jpeg", "X-Device-ID": "camera01", "X-Request-ID": "req-day08-001"}
        self.image = jpeg_bytes()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def upload(self, data=None, headers=None):
        return self.client.post("/api/v1/images", content=self.image if data is None else data,
                                headers=self.headers if headers is None else headers)

    def review(self, record, result="danger"):
        return {"schema": "physlab.vision.result.v1", "device_id": "camera01",
                "request_id": record["request_id"], "image_id": record["image_id"],
                "scene": "rlc_series", "result": result, "objects": [],
                "warnings": [{"level": "danger", "code": "POWER_RISK", "message": "人工检查发现风险"}],
                "suggestion": "人工复核：先停止实验并检查。", "source": "manual"}

    def test_day08_upload_and_actual_jpeg_download(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        record = response.json()
        self.assertEqual(record["received_bytes"], len(self.image))
        metadata = self.client.get(f"/api/v1/images/{record['image_id']}").json()
        self.assertEqual(metadata["vision"]["result"], "unknown")
        self.assertEqual(metadata["vision"]["source"], "unconfigured")
        self.assertEqual(self.client.get(f"/api/v1/images/{record['image_id']}/file").content, self.image)
        self.assertEqual(len(self.app.state.store.pending()), 1)

    def test_duplicate_upload_is_idempotent_even_after_restart(self):
        first = self.upload().json()
        restarted = ImageStore(self.root)
        second = restarted.accept("req-day08-001", "camera01", "rlc_series", self.image)
        self.assertEqual(first["image_id"], second["image_id"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(restarted.pending()), 1)

    def test_request_id_collision_rejects_different_image(self):
        self.upload()
        self.assertEqual(self.upload(jpeg_bytes("black")).status_code, 409)
        self.assertEqual(len(self.app.state.store.recent()), 1)

    def test_fake_jpeg_markers_do_not_pass_decode(self):
        self.assertEqual(self.upload(b"\xff\xd8not-a-jpeg\xff\xd9").status_code, 400)
        self.assertEqual(self.app.state.store.pending(), [])

    def test_oversized_body_rejected_without_saving(self):
        self.assertEqual(self.upload(b"x" * (MAX_IMAGE_BYTES + 1)).status_code, 413)
        self.assertEqual(self.app.state.store.recent(), [])

    def test_invalid_content_type_device_and_traversal(self):
        for name, value, expected in [("Content-Type", "text/plain", 415),
                                      ("X-Device-ID", "other", 400),
                                      ("X-Request-ID", "../../escape", 400)]:
            with self.subTest(name=name):
                self.assertEqual(self.upload(headers={**self.headers, name: value}).status_code, expected)

    def test_manual_danger_result_persists_and_is_idempotent(self):
        record = self.upload().json()
        payload = self.review(record)
        url = f"/api/v1/images/{record['image_id']}/result"
        self.assertEqual(self.client.post(url, json=payload).status_code, 200)
        self.assertEqual(self.client.post(url, json=payload).status_code, 200)
        self.assertEqual(len(self.app.state.store.pending()), 2)
        self.assertEqual(ImageStore(self.root).get(record["image_id"])["vision"]["result"], "danger")

    def test_mismatched_request_and_conflicting_severity_rejected(self):
        record = self.upload().json()
        payload = self.review(record)
        url = f"/api/v1/images/{record['image_id']}/result"
        payload["request_id"] = "wrong-request"
        self.assertEqual(self.client.post(url, json=payload).status_code, 409)
        payload["request_id"] = record["request_id"]
        payload["result"] = "ok"
        self.assertEqual(self.client.post(url, json=payload).status_code, 422)

    def test_model_source_cannot_be_claimed_by_manual_endpoint(self):
        record = self.upload().json()
        payload = self.review(record)
        payload["source"] = "model"
        self.assertEqual(self.client.post(f"/api/v1/images/{record['image_id']}/result", json=payload).status_code, 422)

    def test_outbox_ack_is_persistent(self):
        self.upload()
        pending = self.app.state.store.pending()
        self.app.state.store.mark_sent(pending[0]["id"])
        self.assertEqual(ImageStore(self.root).pending(), [])


if __name__ == "__main__":
    unittest.main()
