import argparse
import json

import httpx


def main():
    parser = argparse.ArgumentParser(description="人工复核图片，向 B 板发布明确标记为 manual 的结果")
    parser.add_argument("image_id")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--result", choices=["ok", "warning", "danger", "unknown"], required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--code", default="MANUAL_REVIEW")
    args = parser.parse_args()
    with httpx.Client(base_url=args.server, timeout=10, trust_env=False) as client:
        response = client.get(f"/api/v1/images/{args.image_id}")
        response.raise_for_status()
        metadata = response.json()
        payload = {"schema": "physlab.vision.result.v1", "device_id": "camera01",
                   "request_id": metadata["request_id"], "image_id": args.image_id,
                   "scene": metadata["scene"], "result": args.result, "objects": [],
                   "warnings": [], "suggestion": args.message, "source": "manual"}
        if args.result in {"warning", "danger"}:
            payload["warnings"] = [{"level": args.result, "code": args.code, "message": args.message}]
        response = client.post(f"/api/v1/images/{args.image_id}/result", json=payload)
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
