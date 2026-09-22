from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def validate_request_id(request_id: str) -> str:
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Request-ID",
        )
    return request_id


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/images")
async def upload_image(
    request: Request,
    x_device_id: str = Header(default="unknown"),
    x_request_id: str = Header(default=""),
):
    request_id = validate_request_id(x_request_id)

    content_type = request.headers.get("content-type", "")
    if content_type != "image/jpeg":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be image/jpeg",
        )

    image_bytes = await request.body()

    if len(image_bytes) < 4:
        raise HTTPException(status_code=400, detail="Image is too small")

    if not (
        image_bytes.startswith(b"\xff\xd8")
        and image_bytes.endswith(b"\xff\xd9")
    ):
        raise HTTPException(status_code=400, detail="Invalid JPEG markers")

    image_id = f"img-{uuid.uuid4().hex[:12]}"
    file_name = f"{request_id}_{image_id}.jpg"
    image_path = UPLOAD_DIR / file_name

    image_path.write_bytes(image_bytes)

    received_at = datetime.now(timezone.utc).isoformat()

    print(
        f"uploaded request_id={request_id} "
        f"device_id={x_device_id} "
        f"bytes={len(image_bytes)} "
        f"file={image_path}"
    )

    return JSONResponse(
        status_code=201,
        content={
            "image_id": image_id,
            "request_id": request_id,
            "received_bytes": len(image_bytes),
            "status": "queued",
            "received_at": received_at,
        },
    )