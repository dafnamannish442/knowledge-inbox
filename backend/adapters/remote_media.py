from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from backend.adapters.base import FetchedContent, SourceAdapter
from backend.adapters.utils import download_file


class RemoteMediaAdapter(SourceAdapter):
    source_type = "remote_media"
    _suffixes = {
        ".aac",
        ".avi",
        ".flac",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".m3u8",
        ".ogg",
        ".opus",
        ".wav",
        ".webm",
    }

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return False
        return Path(urlparse(value).path).suffix.lower() in cls._suffixes

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        if not self.config.download_remote_media:
            raise RuntimeError("远程媒体摄入需要启用 download_remote_media")
        url = str(value)
        stem = unquote(Path(urlparse(url).path).stem).strip() or "Remote media"
        title = str(kwargs.get("title") or stem)
        if Path(urlparse(url).path).suffix.lower() == ".m3u8":
            path = await asyncio.to_thread(self._download_hls, url)
            capture_mode = "hls"
        else:
            path = await download_file(
                url,
                self.config.data_dir / "originals" / "remote_media",
                self.config.max_download_mb,
                referer=url,
                filename=stem,
            )
            capture_mode = "direct_download"
        return FetchedContent(
            source_type=self.source_type,
            source_url=url,
            title=title,
            media_files=[path],
            metadata={"capture_mode": capture_mode},
        )

    def _download_hls(self, url: str) -> str:
        try:
            import yt_dlp
        except ImportError as error:
            raise RuntimeError("HLS 摄入需要安装 yt-dlp") from error
        output_dir = self.config.data_dir / "originals" / "remote_media"
        output_dir.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": str(output_dir / "%(id)s-%(title).80s.%(ext)s"),
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "max_filesize": self.config.max_download_mb * 1024 * 1024,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            prepared = Path(downloader.prepare_filename(info))
        candidates = [
            Path(download["filepath"])
            for download in info.get("requested_downloads") or []
            if download.get("filepath") and Path(download["filepath"]).is_file()
        ]
        if prepared.is_file():
            candidates.append(prepared)
        if prepared.with_suffix(".mp4").is_file():
            candidates.append(prepared.with_suffix(".mp4"))
        if not candidates:
            raise RuntimeError("HLS 下载完成但未找到媒体文件")
        return str(max(candidates, key=lambda path: path.stat().st_size))
