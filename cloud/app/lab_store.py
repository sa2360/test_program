from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from app.experiments import experiment_ids
from app.protocol import ALARM_TOPIC


class LabError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: object, name: str, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise LabError(422, f"{name} must be text")
    result = value.strip()
    if not minimum <= len(result) <= maximum:
        raise LabError(422, f"{name} must be {minimum}-{maximum} characters")
    return result


def category_for(question: str) -> str:
    text = question.lower()
    categories = (
        ("接线与安全", ("接线", "短路", "过流", "过压", "发热", "危险", "电源", "断电", "异味")),
        ("参数与公式", ("频率", "谐振", "公式", "电阻", "电感", "电容", "品质", "q值", "rlc")),
        ("数据与误差", ("数据", "误差", "测量", "读数", "拟合", "记录", "偏差")),
        ("操作与仪器", ("示波器", "信号源", "万用表", "扫频", "电桥", "检流计", "触发")),
    )
    for category, terms in categories:
        if any(term in text for term in terms):
            return category
    return "其他"


class LabStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "index.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS qa_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment TEXT NOT NULL, question TEXT NOT NULL,
                    category TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS teacher_questions (
                    question_id TEXT PRIMARY KEY, student_name TEXT NOT NULL,
                    experiment TEXT NOT NULL, question TEXT NOT NULL,
                    category TEXT NOT NULL, created_at TEXT NOT NULL,
                    reply TEXT, replied_at TEXT
                );
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY, student_name TEXT NOT NULL,
                    experiment TEXT NOT NULL, title TEXT NOT NULL,
                    columns_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dataset_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_id TEXT NOT NULL,
                    values_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
                );
                CREATE TABLE IF NOT EXISTS capture_requests (
                    request_id TEXT PRIMARY KEY, experiment TEXT NOT NULL,
                    created_at TEXT NOT NULL
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

    @staticmethod
    def _experiment(value: object) -> str:
        experiment = _text(value, "experiment", 64)
        if experiment not in experiment_ids():
            raise LabError(422, "unknown experiment")
        return experiment

    @staticmethod
    def _table_exists(db: sqlite3.Connection, name: str) -> bool:
        return db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def validate_question(self, experiment: object, question: object) -> tuple[str, str]:
        return self._experiment(experiment), _text(question, "question", 500)

    def record_qa(self, experiment: object, question: object, source: object) -> None:
        selected, asked = self.validate_question(experiment, question)
        answer_source = _text(source, "source", 40)
        with self.db() as db:
            db.execute(
                "INSERT INTO qa_logs(experiment,question,category,source,created_at) VALUES (?,?,?,?,?)",
                (selected, asked, category_for(asked), answer_source, _now()),
            )

    def add_teacher_question(self, student_name: object, experiment: object, question: object) -> dict:
        name = _text(student_name, "student_name", 60)
        selected = self._experiment(experiment)
        asked = _text(question, "question", 500)
        record = {
            "question_id": f"teacher-q-{uuid.uuid4().hex}",
            "student_name": name,
            "experiment": selected,
            "question": asked,
            "category": category_for(asked),
            "created_at": _now(),
            "reply": None,
            "replied_at": None,
        }
        with self.db() as db:
            db.execute(
                "INSERT INTO teacher_questions VALUES (?,?,?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    @staticmethod
    def _question_record(row: sqlite3.Row) -> dict:
        return dict(row)

    def teacher_questions(self) -> list[dict]:
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM teacher_questions ORDER BY reply IS NOT NULL, created_at DESC"
            ).fetchall()
        return [self._question_record(row) for row in rows]

    def student_questions(self, student_name: object) -> list[dict]:
        name = _text(student_name, "student_name", 60)
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM teacher_questions WHERE student_name=? ORDER BY created_at DESC", (name,)
            ).fetchall()
        return [self._question_record(row) for row in rows]

    def reply_to_question(self, question_id: str, reply: object) -> dict:
        text = _text(reply, "reply", 800)
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM teacher_questions WHERE question_id=?", (question_id,)
            ).fetchone()
            if row is None:
                raise LabError(404, "teacher question not found")
            replied_at = _now()
            db.execute(
                "UPDATE teacher_questions SET reply=?, replied_at=? WHERE question_id=?",
                (text, replied_at, question_id),
            )
            return {**dict(row), "reply": text, "replied_at": replied_at}

    def create_dataset(
        self, student_name: object, experiment: object, title: object, columns: object
    ) -> dict:
        name = _text(student_name, "student_name", 60)
        selected = self._experiment(experiment)
        dataset_title = _text(title, "title", 80)
        if not isinstance(columns, list) or not 1 <= len(columns) <= 8:
            raise LabError(422, "columns must contain 1-8 names")
        clean_columns = [_text(item, "column", 32) for item in columns]
        if len({item.casefold() for item in clean_columns}) != len(clean_columns):
            raise LabError(422, "column names must be unique")
        record = {
            "dataset_id": f"data-{uuid.uuid4().hex}",
            "student_name": name,
            "experiment": selected,
            "title": dataset_title,
            "columns": clean_columns,
            "created_at": _now(),
        }
        with self.db() as db:
            db.execute(
                "INSERT INTO datasets VALUES (?,?,?,?,?,?)",
                (record["dataset_id"], name, selected, dataset_title,
                 json.dumps(clean_columns, ensure_ascii=False), record["created_at"]),
            )
        return {**record, "rows": []}

    def list_datasets(self, student_name: object) -> list[dict]:
        name = _text(student_name, "student_name", 60)
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM datasets WHERE student_name=? ORDER BY created_at DESC", (name,)
            ).fetchall()
        return [{**dict(row), "columns": json.loads(row["columns_json"])} for row in rows]

    def dataset(self, dataset_id: str) -> dict:
        with self.db() as db:
            dataset = db.execute("SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
            if dataset is None:
                raise LabError(404, "dataset not found")
            rows = db.execute(
                "SELECT id,values_json,created_at FROM dataset_rows WHERE dataset_id=? ORDER BY id", (dataset_id,)
            ).fetchall()
        record = dict(dataset)
        record["columns"] = json.loads(record.pop("columns_json"))
        record["rows"] = [
            {"id": row["id"], "values": json.loads(row["values_json"]), "created_at": row["created_at"]}
            for row in rows
        ]
        return record

    def add_dataset_row(self, dataset_id: str, values: object) -> dict:
        if not isinstance(values, list):
            raise LabError(422, "values must be an array")
        with self.db() as db:
            dataset = db.execute("SELECT columns_json FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
            if dataset is None:
                raise LabError(404, "dataset not found")
            columns = json.loads(dataset["columns_json"])
            if len(values) != len(columns):
                raise LabError(422, "values must match the number of columns")
            clean_values = []
            for value in values:
                if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                    raise LabError(422, "each value must be text or a number")
                cell = str(value).strip()
                if not cell or len(cell) > 64:
                    raise LabError(422, "each value must contain 1-64 characters")
                clean_values.append(cell)
            created_at = _now()
            cursor = db.execute(
                "INSERT INTO dataset_rows(dataset_id,values_json,created_at) VALUES (?,?,?)",
                (dataset_id, json.dumps(clean_values, ensure_ascii=False), created_at),
            )
        return {"id": cursor.lastrowid, "values": clean_values, "created_at": created_at}

    def record_capture(self, request_id: str, experiment: object) -> dict:
        selected = self._experiment(experiment)
        record = {"request_id": request_id, "experiment": selected, "created_at": _now()}
        with self.db() as db:
            db.execute("INSERT INTO capture_requests VALUES (?,?,?)", tuple(record.values()))
        return record

    def capture(self, request_id: str) -> dict:
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM capture_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None:
                raise LabError(404, "capture request not found")
            image = None
            if self._table_exists(db, "images"):
                image_row = db.execute(
                    "SELECT metadata,result FROM images WHERE request_id=?", (request_id,)
                ).fetchone()
                if image_row:
                    image = {**json.loads(image_row["metadata"]), "vision": json.loads(image_row["result"])}
        return {**dict(row), "status": "received" if image else "queued", "image": image}

    def upload_experiment(self, request_id: str, declared: str | None) -> str:
        """Day08 cameras omit the experiment header; use the saved web request."""
        with self.db() as db:
            row = db.execute(
                "SELECT experiment FROM capture_requests WHERE request_id=?", (request_id,)
            ).fetchone()
        if row:
            if declared is not None and declared != row["experiment"]:
                raise LabError(409, "Upload experiment does not match capture request")
            return row["experiment"]
        return declared if declared is not None else "rlc_series"

    def insights(self) -> dict:
        with self.db() as db:
            qa_rows = db.execute("SELECT question,category,created_at FROM qa_logs").fetchall()
            teacher_rows = db.execute(
                "SELECT question,category,created_at FROM teacher_questions"
            ).fetchall()
            event_rows = []
            image_rows = []
            if self._table_exists(db, "events"):
                event_rows = db.execute(
                    "SELECT received_at,payload FROM events WHERE topic=?", (ALARM_TOPIC,)
                ).fetchall()
            if self._table_exists(db, "images"):
                image_rows = db.execute("SELECT metadata,result FROM images").fetchall()

        questions = [*qa_rows, *teacher_rows]
        categories = Counter(row["category"] for row in questions)
        normalized: dict[str, tuple[str, int]] = {}
        for row in questions:
            key = " ".join(row["question"].lower().split())
            original, count = normalized.get(key, (row["question"], 0))
            normalized[key] = (original, count + 1)
        frequent = [
            {"question": original, "count": count}
            for original, count in sorted(normalized.values(), key=lambda item: (-item[1], item[0]))[:5]
        ]

        warning_codes: Counter[str] = Counter()
        reviewed_images = 0
        danger_images = 0
        timestamps = [row["created_at"] for row in questions]
        for row in image_rows:
            metadata = json.loads(row["metadata"])
            result = json.loads(row["result"])
            timestamps.append(metadata.get("received_at", ""))
            if result.get("result") == "unknown":
                continue
            reviewed_images += 1
            if result.get("result") == "danger":
                danger_images += 1
            for warning in result.get("warnings", []):
                warning_codes[warning.get("code", "未分类")] += 1

        alarms: Counter[str] = Counter()
        for row in event_rows:
            timestamps.append(row["received_at"])
            payload = json.loads(row["payload"])
            alarms[payload.get("code", "未分类")] += 1

        top_categories = [
            {"category": category, "count": count}
            for category, count in categories.most_common(5)
        ]
        top_warnings = [{"code": code, "count": count} for code, count in warning_codes.most_common(5)]
        top_alarms = [{"code": code, "count": count} for code, count in alarms.most_common(5)]
        leads = {
            "接线与安全": "安排一次断电核线和上电前检查的现场示范。",
            "参数与公式": "用一组实测参数演示公式适用条件与单位换算。",
            "数据与误差": "增加原始记录、重复测量和误差来源讨论的示范。",
            "操作与仪器": "在正式测量前演示仪器量程、触发和读数设置。",
            "其他": "预留集中答疑时间并补充对应实验步骤说明。",
        }
        suggestions = []
        if top_categories:
            item = top_categories[0]
            suggestions.append({
                "text": leads[item["category"]],
                "basis": f"依据：已记录 {item['count']} 条“{item['category']}”类学生问题。",
            })
        if frequent and frequent[0]["count"] >= 2:
            item = frequent[0]
            suggestions.append({
                "text": "将重复出现的问题加入课前检查单或课堂示范。",
                "basis": f"依据：同类问题“{item['question']}”出现 {item['count']} 次。",
            })
        if danger_images:
            suggestions.append({
                "text": "上电前增加一次由教师或同伴完成的安全复核。",
                "basis": f"依据：人工复核图片中有 {danger_images} 条危险结果。",
            })
        elif top_warnings:
            item = top_warnings[0]
            suggestions.append({
                "text": "针对出现的视觉复核问题补充操作提醒。",
                "basis": f"依据：人工或模型结果中的告警“{item['code']}”出现 {item['count']} 次。",
            })
        if top_alarms:
            item = top_alarms[0]
            suggestions.append({
                "text": "复盘设备告警对应的操作条件，并在实验前说明停止条件。",
                "basis": f"依据：设备告警“{item['code']}”出现 {item['count']} 次。",
            })
        if not suggestions:
            suggestions.append({
                "text": "尚无足够的真实课堂记录，暂不生成针对性授课结论。",
                "basis": "依据：当前没有学生问题、人工视觉结果或设备告警。",
            })
        valid_times = [value for value in timestamps if value]
        return {
            "window": {"from": min(valid_times) if valid_times else None, "to": max(valid_times) if valid_times else None},
            "question_count": len(questions),
            "categories": top_categories,
            "frequent_questions": frequent,
            "reviewed_image_count": reviewed_images,
            "warning_codes": top_warnings,
            "alarms": top_alarms,
            "suggestions": suggestions[:4],
        }
