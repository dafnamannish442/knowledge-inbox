from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContentItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    source_type: str
    source_url: str | None = None
    title: str = "未命名知识"
    author: str | None = None
    created_time: datetime | None = None
    raw_content: str = ""
    media_files: list[str] = Field(default_factory=list)
    transcript: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    related_notes: list[str] = Field(default_factory=list)
    importance_score: float = Field(default=0.5, ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    title: str | None = None
    source_type: str | None = None


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    input_type: str
    payload: dict[str, Any]
    item_id: str | None = None
    note_path: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def local_path(self) -> Path | None:
        value = self.payload.get("path")
        return Path(value) if value else None
