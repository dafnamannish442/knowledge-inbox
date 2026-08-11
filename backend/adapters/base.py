from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.config import AppConfig
from backend.models import ContentItem


@dataclass(slots=True)
class FetchedContent:
    source_type: str
    source_url: str | None = None
    title: str = "未命名知识"
    author: str | None = None
    raw_content: str = ""
    transcript: str | None = None
    media_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(ABC):
    source_type = "unknown"

    def __init__(self, config: AppConfig):
        self.config = config

    @classmethod
    @abstractmethod
    def detect(cls, value: str | Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fetch(self, value: str | Path, **kwargs: Any) -> FetchedContent:
        raise NotImplementedError

    def normalize(self, fetched: FetchedContent) -> ContentItem:
        return ContentItem(
            source_type=fetched.source_type,
            source_url=fetched.source_url,
            title=fetched.title.strip() or "未命名知识",
            author=fetched.author,
            raw_content=fetched.raw_content.strip(),
            transcript=fetched.transcript,
            media_files=fetched.media_files,
            metadata=fetched.metadata,
        )
