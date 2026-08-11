from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from backend.adapters import AdapterRegistry
from backend.models import ContentItem, Job
from backend.processors.ai import AIProcessor
from backend.processors.cleaner import clean_text
from backend.processors.linker import KnowledgeLinker
from backend.processors.transcriber import Transcriber
from backend.storage.db import Database
from backend.storage.obsidian import ObsidianWriter


class ContentPipeline:
    def __init__(
        self,
        registry: AdapterRegistry,
        database: Database,
        writer: ObsidianWriter,
        ai: AIProcessor,
        linker: KnowledgeLinker,
    ):
        self.registry = registry
        self.database = database
        self.writer = writer
        self.ai = ai
        self.linker = linker
        self.transcriber = Transcriber()

    async def process(self, job: Job) -> tuple[ContentItem, Path]:
        item = await self._extract(job)
        item.raw_content = clean_text(item.raw_content)
        if item.transcript:
            item.transcript = clean_text(item.transcript)
        elif item.media_files:
            item.transcript = await self.transcriber.transcribe_first(item.media_files)
        if (
            self._has_audio_media(item.media_files)
            and not item.transcript
            and not item.raw_content
            and not self.ai.supports_video
        ):
            raise RuntimeError("未生成转写文本；请安装 media 依赖并确认 ffmpeg 可用")

        analysis = await self.ai.analyze(item)
        item.summary = str(analysis.get("summary") or "")
        item.category = str(analysis.get("category") or "待分类")
        item.tags = self._strings(analysis.get("tags"))
        item.keywords = self._strings(analysis.get("keywords"))
        item.importance_score = max(0, min(1, float(analysis.get("importance_score", 0.5))))
        item.metadata["core_points"] = self._strings(analysis.get("core_points"))
        item.metadata["key_data"] = self._strings(analysis.get("key_data"))
        item.metadata["actions"] = self._strings(analysis.get("actions"))
        description = str(
            analysis.get("media_description") or analysis.get("image_description") or ""
        ).strip()
        if description:
            item.metadata["media_description"] = description
        if (
            item.source_type == "image"
            and not item.raw_content
            and not item.metadata.get("media_description")
        ):
            raise RuntimeError("图片 OCR 和视觉模型均未产出内容；请安装 OCR 或启用 vision_model")
        item.related_notes = await asyncio.to_thread(self.linker.find_related, item)

        videos_to_delete = self._videos_to_delete(item)
        if videos_to_delete:
            item.metadata["deleted_video_files"] = [path.name for path in videos_to_delete]
            item.media_files = [
                value for value in item.media_files if Path(value).resolve() not in videos_to_delete
            ]
        note_path = await asyncio.to_thread(self.writer.write, item)
        await asyncio.to_thread(self.database.save_item, item, str(note_path))
        for path in videos_to_delete:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        return item, note_path

    async def _extract(self, job: Job) -> ContentItem:
        title = job.payload.get("title")
        if job.input_type == "text":
            return ContentItem(
                source_type=job.payload.get("source_type") or "text",
                title=title or "随手记录",
                raw_content=job.payload["text"],
            )
        if job.input_type == "url":
            adapter = self.registry.for_url(job.payload["url"])
            return adapter.normalize(await adapter.fetch(job.payload["url"], title=title))
        if job.input_type == "file":
            path = job.local_path()
            if not path or not path.exists():
                raise FileNotFoundError(f"上传文件不存在: {path}")
            adapter = self.registry.for_file(path)
            item = adapter.normalize(await adapter.fetch(path, title=title))
            item.source_url = job.payload.get("source_url")
            return item
        raise ValueError(f"未知输入类型: {job.input_type}")

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(part).strip() for part in value if str(part).strip()]

    @staticmethod
    def _has_audio_media(paths: list[str]) -> bool:
        suffixes = {
            ".aac",
            ".avi",
            ".flac",
            ".m4a",
            ".m4v",
            ".mkv",
            ".mov",
            ".mp3",
            ".mp4",
            ".ogg",
            ".opus",
            ".wav",
            ".webm",
        }
        return any(Path(path).suffix.lower() in suffixes for path in paths)

    def _videos_to_delete(self, item: ContentItem) -> list[Path]:
        if not self.writer.config.delete_video_after_ingest:
            return []
        originals = (self.writer.config.data_dir / "originals").resolve()
        suffixes = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
        return [
            path
            for value in item.media_files
            if (path := Path(value).resolve()).suffix.lower() in suffixes
            and path.is_relative_to(originals)
        ]
