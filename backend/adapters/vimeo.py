from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from backend.adapters.base import FetchedContent, SourceAdapter
from backend.adapters.utils import fetch_bytes, subtitle_to_text


class VimeoAdapter(SourceAdapter):
    source_type = "vimeo"
    _pattern = re.compile(r"https?://(?:www\.)?(?:vimeo\.com|player\.vimeo\.com)/")

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, str) and bool(cls._pattern.match(value))

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        url = str(value)
        query = urlencode({"url": url})
        body, _ = await fetch_bytes(
            f"https://vimeo.com/api/oembed.json?{query}", max_mb=2, referer=url
        )
        try:
            oembed = json.loads(body)
        except json.JSONDecodeError as error:
            raise RuntimeError("Vimeo oEmbed 返回无效数据") from error
        media_path, transcript, metadata = await asyncio.to_thread(self._resolve_media, url)
        if not media_path and not transcript:
            raise RuntimeError("Vimeo 视频没有可用字幕；请启用 download_remote_media 后重试")
        return FetchedContent(
            source_type=self.source_type,
            source_url=url,
            title=str(kwargs.get("title") or oembed.get("title") or "Vimeo video"),
            author=oembed.get("author_name"),
            transcript=transcript,
            media_files=[media_path] if media_path else [],
            metadata={
                **metadata,
                "thumbnail_url": oembed.get("thumbnail_url"),
                "provider": "vimeo",
            },
        )

    def _resolve_media(self, url: str) -> tuple[str | None, str | None, dict[str, Any]]:
        try:
            import yt_dlp
        except ImportError as error:
            raise RuntimeError("Vimeo Adapter 需要安装 yt-dlp") from error

        output_dir = self.config.data_dir / "originals" / "vimeo"
        output_dir.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": not self.config.download_remote_media,
            "outtmpl": str(output_dir / "%(id)s-%(title).80s.%(ext)s"),
            "noplaylist": True,
            "max_filesize": self.config.max_download_mb * 1024 * 1024,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh-Hans", "zh", "en", "en-US", "en-GB"],
            "subtitlesformat": "vtt/best",
        }
        if self.config.download_remote_media:
            options.update(
                {
                    "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                    "merge_output_format": "mp4",
                }
            )
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=self.config.download_remote_media)

        video_id = str(info.get("id") or self._video_id(url) or "")
        transcript = self._read_subtitle(info, output_dir, video_id)
        media_path = self._downloaded_path(info, output_dir, video_id)
        return (
            media_path,
            transcript,
            {
                "duration": info.get("duration"),
                "upload_date": info.get("upload_date"),
                "channel_url": info.get("channel_url") or info.get("uploader_url"),
            },
        )

    @staticmethod
    def _read_subtitle(info: dict[str, Any], output_dir: Path, video_id: str) -> str | None:
        candidates: list[Path] = []
        for subtitle in (info.get("requested_subtitles") or {}).values():
            if path := subtitle.get("filepath"):
                candidates.append(Path(path))
        candidates.extend(output_dir.glob(f"{video_id}-*.vtt"))
        candidates.extend(output_dir.glob(f"{video_id}-*.srt"))
        for path in candidates:
            if not path.is_file():
                continue
            text = subtitle_to_text(path.read_text("utf-8", errors="replace"))
            path.unlink(missing_ok=True)
            if text:
                return text
        return None

    @staticmethod
    def _downloaded_path(
        info: dict[str, Any], output_dir: Path, video_id: str
    ) -> str | None:
        for download in info.get("requested_downloads") or []:
            if (path := download.get("filepath")) and Path(path).is_file():
                return str(Path(path))
        if (filename := info.get("_filename")) and Path(filename).is_file():
            return str(Path(filename))
        suffixes = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
        matches = [
            path
            for path in output_dir.glob(f"{video_id}-*")
            if path.is_file() and path.suffix.lower() in suffixes
        ]
        return str(max(matches, key=lambda path: path.stat().st_size)) if matches else None

    @staticmethod
    def _video_id(url: str) -> str | None:
        parts = [part for part in urlparse(url).path.split("/") if part]
        return next((part for part in reversed(parts) if part.isdigit()), None)
