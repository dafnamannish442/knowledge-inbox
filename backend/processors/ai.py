from __future__ import annotations

import asyncio
import base64
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from backend.config import AIConfig
from backend.models import ContentItem


SYSTEM_PROMPT = """你是个人知识库编辑。根据输入内容输出严格 JSON，不要 Markdown 代码围栏。
字段：
summary: 一句话总结，不超过 80 字；
core_points: 3-7 条核心观点字符串数组；
key_data: 关键数字、事实、原句摘录组成的字符串数组；
actions: 可行动事项字符串数组；
category: 一个稳定、简短的中文分类；
tags: 3-8 个中文或英文标签，不要井号；
keywords: 3-10 个关键词；
importance_score: 0 到 1 的数字；
media_description: 若有图片或视频，描述画面、图表关系、重要文字和音视频内容，否则为空字符串。
忠于原文；证据不足时明确写“原文未提供”，不要臆测。"""


class AIProcessor:
    def __init__(self, config: AIConfig):
        self.config = config

    @property
    def supports_video(self) -> bool:
        return self.config.enabled and bool(self.config.vision_model)

    async def analyze(self, item: ContentItem) -> dict[str, Any]:
        text = "\n\n".join(filter(None, [item.raw_content, item.transcript]))
        if not self.config.enabled:
            return self._fallback(text)

        user_content: str | list[dict[str, Any]] = (
            f"标题：{item.title}\n来源：{item.source_type}\n\n{text[:80_000]}"
        )
        video_path = self._first_video(item.media_files)
        image_path = self._first_image(item.media_files)
        prepared_video: Path | None = None
        model = self.config.model
        if video_path and self.config.vision_model:
            prepared_video = await asyncio.to_thread(self._prepare_video, video_path)
            model = self.config.vision_model
            encoded = base64.b64encode(prepared_video.read_bytes()).decode("ascii")
            user_content = [
                {"type": "text", "text": str(user_content)},
                {
                    # The local Antigravity OpenAI-compatible endpoint accepts
                    # video MIME data through image_url, not video_url.
                    "type": "image_url",
                    "image_url": {"url": f"data:video/mp4;base64,{encoded}"},
                },
            ]
        elif image_path and self.config.vision_model:
            model = self.config.vision_model
            mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            user_content = [
                {"type": "text", "text": str(user_content)},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                },
            ]

        headers = {"Content-Type": "application/json"}
        if self.config.api_key and self.config.api_key.strip():
            headers["Authorization"] = f"Bearer {self.config.api_key.strip()}"
        payload = {
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        try:
            print(f"[AIProcessor] Posting to {self.config.base_url.rstrip('/')}/chat/completions with model {model}")
            async with httpx.AsyncClient(
                timeout=max(self.config.timeout_seconds, 180),
                trust_env=False,
            ) as client:
                response = await client.post(
                    f"{self.config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        finally:
            if prepared_video and prepared_video != video_path:
                prepared_video.unlink(missing_ok=True)
        content = response.json()["choices"][0]["message"]["content"]
        try:
            result = self._parse_json(content)
        except Exception as err:
            print(f"[AIProcessor] JSON Parse error: {err}, raw content: {content[:200]!r}")
            result = {}
        return {**self._fallback(text), **result}

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("AI 返回的结果不是 JSON 对象")
        return result

    @staticmethod
    def _first_image(media_files: list[str]) -> Path | None:
        return next(
            (
                Path(value)
                for value in media_files
                if Path(value).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                and Path(value).exists()
            ),
            None,
        )

    @staticmethod
    def _first_video(media_files: list[str]) -> Path | None:
        return next(
            (
                Path(value)
                for value in media_files
                if Path(value).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
                and Path(value).exists()
            ),
            None,
        )

    @staticmethod
    def _prepare_video(path: Path) -> Path:
        max_bytes = 40 * 1024 * 1024
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        if (
            path.suffix.lower() == ".mp4"
            and path.stat().st_size <= max_bytes
            and probe.stdout.strip() == "h264"
        ):
            return path
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temporary:
            output = Path(temporary.name)
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-vf",
            "scale=-2:480",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "31",
            "-c:a",
            "aac",
            "-ac",
            "1",
            "-b:a",
            "48k",
            "-movflags",
            "+faststart",
            str(output),
        ]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
            if output.stat().st_size > max_bytes:
                raise ValueError("压缩后视频仍超过 40 MB，请先裁剪或压缩")
            return output
        except Exception:
            output.unlink(missing_ok=True)
            raise

    @staticmethod
    def _fallback(text: str) -> dict[str, Any]:
        compact = re.sub(r"\s+", " ", text).strip()
        sentences = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", compact) if part.strip()]
        words = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_-]{2,}", compact.lower())
        stop = {"这个", "一个", "可以", "进行", "以及", "我们", "the", "and", "that", "with"}
        keywords = [word for word, _ in Counter(word for word in words if word not in stop).most_common(8)]
        return {
            "summary": (sentences[0] if sentences else compact[:160]) or "暂无可提取文本",
            "core_points": sentences[:5],
            "key_data": [],
            "actions": [],
            "category": "待分类",
            "tags": keywords[:5] or ["待处理"],
            "keywords": keywords,
            "importance_score": 0.5,
            "media_description": "",
        }
