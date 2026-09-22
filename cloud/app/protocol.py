import json
from functools import lru_cache
from pathlib import Path
import time
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_DIRECTORY = Path(__file__).resolve().parents[2] / "protocol" / "schemas"

ASSISTANT_QUESTION_TOPIC = "physlab/assistant/question"
ASSISTANT_ANSWER_TOPIC = "physlab/assistant/answer"
SENSOR_STATUS_TOPIC = "physlab/sensor01/status"
SENSOR_DATA_TOPIC = "physlab/sensor01/data"
SENSOR_COMMAND_TOPIC = "physlab/sensor01/cmd"
CAMERA_COMMAND_TOPIC = "physlab/camera01/cmd"
CAMERA_STATUS_TOPIC = "physlab/camera01/status"
VISION_RESULT_TOPIC = "physlab/vision/result"
ALARM_TOPIC = "physlab/alarm"


def unix_ms() -> int:
    return int(time.time() * 1000)


@lru_cache(maxsize=None)
def _validator(schema_filename: str) -> Draft202012Validator:
    path = SCHEMA_DIRECTORY / schema_filename
    with path.open("r", encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_message(schema_filename: str, payload: dict[str, Any]) -> None:
    _validator(schema_filename).validate(payload)
