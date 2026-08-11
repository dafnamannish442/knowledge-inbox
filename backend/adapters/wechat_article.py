from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify

from backend.adapters.base import FetchedContent
from backend.adapters.utils import download_media, fetch_html, safe_filename
from backend.adapters.webpage import WebAdapter


class WeChatArticleAdapter(WebAdapter):
    source_type = "wechat_article"

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, str) and "mp.weixin.qq.com/s" in value

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        url = str(value)
        html = await fetch_html(url, self.config.playwright_user_data_dir)
        soup = BeautifulSoup(html, "lxml")
        article = soup.select_one("#js_content")
        if not article:
            return await super().fetch(value, **kwargs)

        title_node = soup.select_one("#activity-name, h1.rich_media_title")
        author_node = soup.select_one("#js_name, .rich_media_meta_nickname")
        title = title_node.get_text(" ", strip=True) if title_node else "微信公众号文章"
        image_urls = [
            image.get("data-src") or image.get("src")
            for image in article.select("img")
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
        return FetchedContent(
            source_type=self.source_type,
            source_url=url,
            title=title,
            author=author_node.get_text(" ", strip=True) if author_node else None,
            raw_content=markdownify(str(article), heading_style="ATX", strip=["script", "style"]),
            media_files=media_files,
        )
