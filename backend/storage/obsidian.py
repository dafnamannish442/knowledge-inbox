from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from backend.adapters.utils import safe_filename
from backend.config import AppConfig
from backend.models import ContentItem


class ObsidianWriter:
    def __init__(self, config: AppConfig):
        self.config = config

    def write(self, item: ContentItem) -> Path:
        folder = self.config.vault_dir / self.config.inbox_folder
        folder.mkdir(parents=True, exist_ok=True)
        date = item.created_at.astimezone().strftime("%Y-%m-%d")
        filename = f"{date}-{safe_filename(item.title, item.id)}-{item.id[:8]}.md"
        target = folder / filename
        content = self.format(item)
        with NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
        return target

    @staticmethod
    def format(item: ContentItem) -> str:
        frontmatter = {
            "title": item.title,
            "source": item.source_type,
            "source_url": item.source_url,
            "author": item.author,
            "created": (item.created_time or item.created_at).isoformat(),
            "category": item.category,
            "tags": item.tags,
            "importance": item.importance_score,
            "content_id": item.id,
        }
        yaml_text = yaml.safe_dump(
            frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False
        ).strip()
        core_points = ObsidianWriter._numbered(item.metadata.get("core_points", []))
        key_data = ObsidianWriter._bullets(item.metadata.get("key_data", []))
        actions = ObsidianWriter._bullets(item.metadata.get("actions", []))
        related = ObsidianWriter._bullets([f"[[{note}]]" for note in item.related_notes])
        transcript = f"\n\n## 转写文本\n\n{item.transcript}" if item.transcript else ""
        description = (
            f"\n\n## 媒体理解\n\n{item.metadata['media_description']}"
            if item.metadata.get("media_description")
            else ""
        )
        attachments = ObsidianWriter._attachments(item.media_files)
        return f"""---
{yaml_text}
---

# 一句话总结

{item.summary or "暂无"}

# 核心观点

{core_points or "1. 暂无"}

# 关键数据

{key_data or "- 原文未提供"}

# 我的关联

结合我的已有知识：

{related or "- 暂未发现可靠关联"}

# 可行动事项

{actions or "- 暂无"}

# 原始内容

{item.raw_content or "（无正文，参见转写或附件）"}{transcript}{description}{attachments}
"""

    @staticmethod
    def _numbered(values: list[str]) -> str:
        return "\n".join(f"{index}. {value}" for index, value in enumerate(values, 1))

    @staticmethod
    def _bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values)

    @staticmethod
    def _attachments(paths: list[str]) -> str:
        lines = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                href = path.resolve().as_uri()
            except ValueError:
                continue
            lines.append(f"- [{path.name}]({href})")
        return f"\n\n## 原始附件\n\n{chr(10).join(lines)}" if lines else ""
