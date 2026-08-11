from __future__ import annotations

import asyncio
import json
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify

from backend.adapters.base import FetchedContent, SourceAdapter


class LocalFileAdapter(SourceAdapter):
    source_type = "local_file"
    _suffixes = {".txt", ".md", ".markdown", ".html", ".htm", ".json", ".csv", ".docx"}

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, Path) and value.suffix.lower() in cls._suffixes

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        path = Path(value)
        content = await asyncio.to_thread(self._read, path)
        return FetchedContent(
            source_type=self.source_type,
            title=str(kwargs.get("title") or path.stem),
            raw_content=content,
            media_files=[str(path)],
        )

    @staticmethod
    def _read(path: Path) -> str:
        if path.suffix.lower() == ".docx":
            try:
                from docx import Document
            except ImportError as error:
                raise RuntimeError("DOCX 提取需要安装 python-docx") from error
            return "\n\n".join(paragraph.text for paragraph in Document(path).paragraphs)
        text = path.read_text("utf-8", errors="replace")
        if path.suffix.lower() in {".html", ".htm"}:
            soup = BeautifulSoup(text, "lxml")
            return markdownify(str(soup.body or soup), heading_style="ATX")
        if path.suffix.lower() == ".json":
            try:
                return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        return text
