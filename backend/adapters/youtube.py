from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from backend.adapters.base import FetchedContent, SourceAdapter
class YouTubeAdapter(SourceAdapter):
    source_type = "youtube"
    _pattern = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/")

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, str) and bool(cls._pattern.match(value))

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        return await asyncio.to_thread(self._fetch_sync, str(value))

    def _fetch_sync(self, url: str) -> FetchedContent:
        try:
            import yt_dlp
        except ImportError as error:
            raise RuntimeError("YouTube Adapter 需要安装 yt-dlp") from error

        output_dir = self.config.data_dir / "originals" / "youtube"
        output_dir.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": not self.config.download_remote_media,
            "outtmpl": str(output_dir / "%(id)s-%(title).80s.%(ext)s"),
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=self.config.download_remote_media)

        transcript = self._transcript(str(info.get("id") or ""))
        media_files = []
        if self.config.download_remote_media:
            path = self._downloaded_path(info, output_dir)
            if path:
                media_files.append(path)
        return FetchedContent(
            source_type=self.source_type,
            source_url=url,
            title=str(info.get("title") or "YouTube Video"),
            author=info.get("uploader") or info.get("channel"),
            raw_content=str(info.get("description") or ""),
            transcript=transcript,
            media_files=media_files,
            metadata={
                "duration": info.get("duration"),
                "upload_date": info.get("upload_date"),
                "channel_url": info.get("channel_url"),
            },
        )

    @staticmethod
    def _transcript(video_id: str) -> str | None:
        if not video_id:
            return None
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            api = YouTubeTranscriptApi()
            entries = api.fetch(video_id, languages=["zh-Hans", "zh", "en"])
            return "\n".join(entry.text for entry in entries)
        except Exception:
            return None

    @staticmethod
    def _downloaded_path(info: dict[str, Any], output_dir: Path) -> str | None:
        for download in info.get("requested_downloads") or []:
            path = download.get("filepath")
            if path and Path(path).exists():
                return str(path)
        filename = info.get("_filename")
        if filename and Path(filename).exists():
            return str(filename)
        video_id = str(info.get("id") or "")
        matches = [path for path in output_dir.glob(f"{video_id}-*") if path.is_file()]
        return str(max(matches, key=lambda path: path.stat().st_size)) if matches else None
