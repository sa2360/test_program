"""Validate both deployed B V1 and A Day08 vision messages."""
from copy import deepcopy

from app.protocol import validate_message


def normalize_vision(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("vision message must be a JSON object")
    if payload.get("schema") == "physlab.vision.v1":
        validate_message("vision.result.v1.schema.json", payload)
        warning = payload["warning"]
        result = {
            "schema": "physlab.vision.result.v1",
            "request_id": payload["request_id"],
            "image_id": payload["image_id"],
            "device_id": "camera01",
            "result": "warning" if warning else "ok",
            "scene": payload["experiment"],
            "objects": payload["objects"],
            "warnings": ([{"level": "warning", "code": warning,
                           "message": payload["message"] or warning}] if warning else []),
            "suggestion": payload["message"] or "旧版视觉结果未提供说明。",
            "ts": payload["ts"],
            "processing_ms": payload["processing_ms"],
        }
    else:
        result = deepcopy(payload)
    validate_message("vision.result.ab.v1.schema.json", result)
    # A normal result must never conceal a warning or danger.
    if result["result"] == "ok" and result["warnings"]:
        raise ValueError("ok result cannot contain warnings")
    if any(w["level"] == "danger" for w in result["warnings"]) and result["result"] != "danger":
        raise ValueError("danger warning requires danger result")
    return result


def unconfigured_result(request_id: str, image_id: str, scene: str) -> dict:
    return normalize_vision({
        "schema": "physlab.vision.result.v1", "request_id": request_id,
        "image_id": image_id, "device_id": "camera01", "result": "unknown",
        "scene": scene, "objects": [], "warnings": [],
        "suggestion": "图片已收到，视觉模型尚未配置；请人工检查实验器材和接线。",
        "source": "unconfigured", "processing_ms": 0,
    })
