from __future__ import annotations

import asyncio
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status

from backend.models import IngestRequest, Job

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "queue_size": request.app.state.worker.queue.qsize(),
        "ai_enabled": request.app.state.config.ai.enabled,
    }


@router.post("/ingest", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
async def ingest(payload: IngestRequest, request: Request) -> Job:
    if bool(payload.url) == bool(payload.text):
        raise HTTPException(422, "url 和 text 必须且只能提供一个")
    input_type = "url" if payload.url else "text"
    job_payload = payload.model_dump(exclude_none=True)
    job = Job(input_type=input_type, payload=job_payload)
    await request.app.state.worker.submit(job)
    return job


@router.post("/upload", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
) -> Job:
    filename = Path(file.filename or "upload.bin").name
    upload_dir = request.app.state.config.data_dir / "originals" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{uuid4().hex[:12]}-{filename}"
    max_bytes = request.app.state.config.max_download_mb * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(413, "上传文件超过大小限制")
                destination.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    job = Job(
        input_type="file",
        payload={
            "path": str(target),
            "title": title or Path(filename).stem,
            "source_url": source_url,
        },
    )
    await request.app.state.worker.submit(job)
    return job


@router.get("/jobs", response_model=list[Job])
async def list_jobs(request: Request, limit: int = 50) -> list[Job]:
    return await asyncio.to_thread(request.app.state.database.list_jobs, min(max(limit, 1), 200))


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, request: Request) -> Job:
    job = await asyncio.to_thread(request.app.state.database.get_job, job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/items")
async def list_items(request: Request, limit: int = 50) -> list[dict[str, str | None]]:
    return await asyncio.to_thread(request.app.state.database.list_items, min(max(limit, 1), 200))


@router.post("/telegram", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
async def telegram(
    payload: dict,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Job:
    expected = request.app.state.config.telegram_webhook_secret
    if expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(403, "Telegram webhook secret 不匹配")

    message = payload.get("message") or payload.get("channel_post") or {}
    text = (message.get("text") or message.get("caption") or "").strip()
    if not text:
        raise HTTPException(422, "当前 webhook 仅接受 Telegram 文字、caption 或链接")
    match = re.search(r"https?://\S+", text)
    if match:
        job = Job(
            input_type="url",
            payload={"url": match.group(0).rstrip(".,，。)"), "title": f"Telegram 转发 {message.get('message_id', '')}"},
        )
    else:
        job = Job(
            input_type="text",
            payload={"text": text, "title": f"Telegram 转发 {message.get('message_id', '')}", "source_type": "telegram"},
        )
    await request.app.state.worker.submit(job)
    return job
