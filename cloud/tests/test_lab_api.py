from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.image_server import create_app
from app.protocol import CAMERA_COMMAND_TOPIC, validate_message


def jpeg_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 24), "white").save(stream, format="JPEG")
    return stream.getvalue()


class LabApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        settings = Settings("127.0.0.1", 1883, "sensor01", "INFO")
        self.app = create_app(Path(self.temp.name), mqtt_enabled=False, settings_override=settings)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_pages_and_three_experiments_are_available(self) -> None:
        experiments = self.client.get("/api/v1/experiments").json()["experiments"]
        self.assertEqual({item["id"] for item in experiments}, {
            "rlc_series", "rlc_transient", "wheatstone_bridge",
        })
        self.assertIn("学生实验助手", self.client.get("/student").text)
        self.assertIn("教师实验看板", self.client.get("/teacher").text)
        self.assertEqual(self.client.get("/assets/student.js").status_code, 200)

    def test_question_reply_and_evidence_based_insight(self) -> None:
        answer = self.client.post("/api/v1/qa", json={
            "experiment": "rlc_series", "question": "谐振频率的公式是什么？",
        })
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json()["source"], "local_knowledge")

        question = self.client.post("/api/v1/teacher/questions", json={
            "student_name": "学生A", "experiment": "rlc_series", "question": "接线前需要断电吗？",
        })
        self.assertEqual(question.status_code, 201)
        question_id = question.json()["question_id"]
        reply = self.client.post(f"/api/v1/teacher/questions/{question_id}/reply", json={
            "reply": "需要，调整元件前先断电并核对公共地。",
        })
        self.assertEqual(reply.status_code, 200)
        mine = self.client.get("/api/v1/student/questions", params={"student_name": "学生A"}).json()
        self.assertEqual(mine[0]["reply"], "需要，调整元件前先断电并核对公共地。")

        insight = self.client.get("/api/v1/teacher/insights").json()
        self.assertEqual(insight["question_count"], 2)
        self.assertTrue(insight["categories"])
        self.assertTrue(all("依据：" in item["basis"] for item in insight["suggestions"]))

    def test_dataset_rows_are_persistent_and_validated(self) -> None:
        dataset = self.client.post("/api/v1/datasets", json={
            "student_name": "学生A", "experiment": "wheatstone_bridge", "title": "平衡读数",
            "columns": ["R1", "R2", "R3", "Rx"],
        })
        self.assertEqual(dataset.status_code, 201)
        dataset_id = dataset.json()["dataset_id"]
        saved = self.client.post(f"/api/v1/datasets/{dataset_id}/rows", json={
            "values": [100, 100, 120, 120],
        })
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()["values"], ["100", "100", "120", "120"])
        self.assertEqual(
            self.client.post(f"/api/v1/datasets/{dataset_id}/rows", json={"values": [1]}).status_code,
            422,
        )
        record = self.client.get(f"/api/v1/datasets/{dataset_id}").json()
        self.assertEqual(len(record["rows"]), 1)

    def test_capture_is_queued_with_deployed_camera_schema(self) -> None:
        response = self.client.post("/api/v1/captures", json={"experiment": "rlc_transient"})
        self.assertEqual(response.status_code, 202)
        queued = response.json()
        command = self.app.state.store.pending()[0]
        self.assertEqual(command["topic"], CAMERA_COMMAND_TOPIC)
        import json
        payload = json.loads(command["payload"])
        validate_message("camera.cmd.v1.schema.json", payload)
        self.assertEqual(payload["request_id"], queued["request_id"])
        status = self.client.get(f"/api/v1/captures/{queued['request_id']}").json()
        self.assertEqual(status["status"], "queued")

    def test_unknown_image_is_excluded_until_manual_review(self) -> None:
        image = self.client.post(
            "/api/v1/images", content=jpeg_bytes(),
            headers={"Content-Type": "image/jpeg", "X-Device-ID": "camera01", "X-Request-ID": "lab-image-1"},
        ).json()
        before = self.client.get("/api/v1/teacher/insights").json()
        self.assertEqual(before["reviewed_image_count"], 0)
        review = {
            "schema": "physlab.vision.result.v1", "device_id": "camera01",
            "request_id": image["request_id"], "image_id": image["image_id"], "scene": "rlc_series",
            "result": "warning", "objects": [],
            "warnings": [{"level": "warning", "code": "MANUAL_WARNING", "message": "人工确认接线需检查"}],
            "suggestion": "断电后检查接线。", "source": "manual",
        }
        self.assertEqual(self.client.post(f"/api/v1/images/{image['image_id']}/result", json=review).status_code, 200)
        after = self.client.get("/api/v1/teacher/insights").json()
        self.assertEqual(after["reviewed_image_count"], 1)
        self.assertEqual(after["warning_codes"][0]["code"], "MANUAL_WARNING")

    def test_day08_upload_uses_selected_experiment_and_rejects_conflict(self) -> None:
        for experiment in ("rlc_transient", "wheatstone_bridge"):
            capture = self.client.post("/api/v1/captures", json={"experiment": experiment}).json()
            headers = {"Content-Type": "image/jpeg", "X-Device-ID": "camera01",
                       "X-Request-ID": capture["request_id"]}
            conflict = self.client.post("/api/v1/images", content=jpeg_bytes(),
                                        headers={**headers, "X-Experiment": "rlc_series"})
            self.assertEqual(conflict.status_code, 409)
            image = self.client.post("/api/v1/images", content=jpeg_bytes(), headers=headers)
            self.assertEqual(image.status_code, 201)
            self.assertEqual(image.json()["scene"], experiment)
            status = self.client.get(f"/api/v1/captures/{capture['request_id']}").json()
            self.assertEqual(status["status"], "received")
            self.assertEqual(status["image"]["vision"]["scene"], experiment)


if __name__ == "__main__":
    unittest.main()
