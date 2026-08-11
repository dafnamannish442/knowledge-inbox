from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx

from backend.adapters.base import FetchedContent, SourceAdapter


class WeChatVideoAdapter(SourceAdapter):
    source_type = "wechat_video"
    _url_pattern = re.compile(
        r"https?://[^ ]*(?:channels\.weixin\.qq\.com|finder\.video\.qq\.com|weixin\.qq\.com/sph/)"
    )
    _video_suffixes = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mp3", ".m4a", ".wav"}

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        if isinstance(value, Path):
            return value.suffix.lower() in cls._video_suffixes
        return bool(cls._url_pattern.match(value))

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        if isinstance(value, Path):
            return FetchedContent(
                source_type=self.source_type,
                title=kwargs.get("title") or value.stem,
                media_files=[str(value)],
                metadata={"capture_mode": "uploaded_file"},
            )

        if not self.config.wechat_video_downloader_url:
            raise RuntimeError(
                "视频号链接抓取需要配置 wechat_video_downloader_url；也可直接上传原始视频"
            )

        base_url = self.config.wechat_video_downloader_url.rstrip("/")
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                timeout=30,
                trust_env=False,
            ) as client:
                response = await client.post("/api/task/create_channels", json={"url": str(value)})
                response.raise_for_status()
                result = response.json()
                if result.get("code") != 0:
                    message = str(result.get("msg") or "未知错误")
                    if "初始化客户端 socket" in message:
                        message = "下载器尚未连接微信客户端"
                    raise RuntimeError(
                        f"wx_channels_download 无法解析视频号链接：{message}"
                    )
                task = result.get("data") or {}
                task_id = str(task.get("id") or "")
                file_path = Path(str(task.get("file_path") or "")).resolve()
                expected_dir = (
                    self.config.data_dir / "originals" / "wechat_video"
                ).resolve()
                if not task_id or not file_path.is_relative_to(expected_dir):
                    raise RuntimeError("wx_channels_download 返回了无效的下载任务")
                title = await self._wait_for_download(client, task_id, file_path)
        except httpx.HTTPError as error:
            raise RuntimeError(
                f"无法连接 wx_channels_download（{base_url}）；请先启动本地下载器"
            ) from error

        return FetchedContent(
            source_type=self.source_type,
            source_url=str(value),
            title=str(kwargs.get("title") or title or file_path.stem).strip(),
            media_files=[str(file_path)],
            metadata={"capture_mode": "wx_channels_download", "download_task_id": task_id},
        )

    async def _wait_for_download(
        self, client: httpx.AsyncClient, task_id: str, file_path: Path
    ) -> str:
        deadline = asyncio.get_running_loop().time() + (
            self.config.wechat_video_download_timeout_seconds
        )
        while asyncio.get_running_loop().time() < deadline:
            response = await client.get("/api/task/list", params={"page_size": 200})
            response.raise_for_status()
            data = response.json().get("data") or {}
            task = next(
                (entry for entry in data.get("list") or [] if entry.get("id") == task_id),
                None,
            )
            if task and task.get("status") == "error":
                raise RuntimeError("wx_channels_download 下载视频失败")
            if task and task.get("status") == "done" and file_path.is_file():
                labels = ((task.get("meta") or {}).get("req") or {}).get("labels") or {}
                return str(labels.get("title") or "")
            await asyncio.sleep(0.5)
        raise RuntimeError("等待 wx_channels_download 下载视频超时")
