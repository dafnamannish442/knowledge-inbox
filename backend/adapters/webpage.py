from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify
from readability import Document

from backend.adapters.base import FetchedContent, SourceAdapter
from backend.adapters.utils import download_media, fetch_html, safe_filename


class WebAdapter(SourceAdapter):
    source_type = "webpage"

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, str) and value.startswith(("http://", "https://"))

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        url = str(value)
        html = await fetch_html(url)
        document = Document(html)
        title = document.short_title() or urlparse(url).netloc
        article_html = document.summary(html_partial=True)
        soup = BeautifulSoup(article_html, "lxml")
        image_urls = [
            image.get("data-src") or image.get("src")
            for image in soup.select("img")
            if image.get("data-src") or image.get("src")
        ]
        media_files: list[str] = []
        if self.config.download_remote_media:
            media_files = await download_media(
                image_urls,
                url,
                self.config.data_dir / "media" / safe_filename(title),
                min(self.config.max_download_mb, 30),
            )

        content = markdownify(article_html, heading_style="ATX", strip=["script", "style"])
        return FetchedContent(
            source_type=self.source_type,
            source_url=url,
            title=title,
            author=self._author(html),
            raw_content=content,
            media_files=media_files,
        )

    @staticmethod
    def _author(html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        for selector, attribute in (
            ('meta[name="author"]', "content"),
            ('meta[property="article:author"]', "content"),
            ('[rel="author"]', None),
        ):
            node = soup.select_one(selector)
            if node:
                value = node.get(attribute) if attribute else node.get_text(" ", strip=True)
                if value:
                    return str(value).strip()
        return None
