from __future__ import annotations

from pathlib import Path

from backend.adapters.base import SourceAdapter
from backend.config import AppConfig


class AdapterRegistry:
    def __init__(self) -> None:
        self._url_adapters: list[SourceAdapter] = []
        self._file_adapters: list[SourceAdapter] = []

    def register_url(self, adapter: SourceAdapter) -> None:
        self._url_adapters.append(adapter)

    def register_file(self, adapter: SourceAdapter) -> None:
        self._file_adapters.append(adapter)

    def for_url(self, url: str) -> SourceAdapter:
        for adapter in self._url_adapters:
            if adapter.detect(url):
                return adapter
        raise ValueError(f"没有 Adapter 可以处理此 URL: {url}")

    def for_file(self, path: Path) -> SourceAdapter:
        for adapter in self._file_adapters:
            if adapter.detect(path):
                return adapter
        raise ValueError(f"不支持的文件类型: {path.suffix or path.name}")


def build_registry(config: AppConfig) -> AdapterRegistry:
    from backend.adapters.image import ImageAdapter
    from backend.adapters.local_file import LocalFileAdapter
    from backend.adapters.pdf import PDFAdapter
    from backend.adapters.twitter import TwitterAdapter
    from backend.adapters.webpage import WebAdapter
    from backend.adapters.wechat_article import WeChatArticleAdapter
    from backend.adapters.wechat_video import WeChatVideoAdapter
    from backend.adapters.youtube import YouTubeAdapter

    registry = AdapterRegistry()
    # Specialized adapters must be checked before the generic web adapter.
    for adapter_type in (
        YouTubeAdapter,
        TwitterAdapter,
        WeChatArticleAdapter,
        WeChatVideoAdapter,
        WebAdapter,
    ):
        registry.register_url(adapter_type(config))
    for adapter_type in (PDFAdapter, ImageAdapter, LocalFileAdapter, WeChatVideoAdapter):
        registry.register_file(adapter_type(config))
    return registry
