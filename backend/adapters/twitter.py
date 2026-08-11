from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from backend.adapters.base import FetchedContent, SourceAdapter
from backend.adapters.utils import download_media, fetch_html, safe_filename


class TwitterAdapter(SourceAdapter):
    source_type = "twitter"
    _pattern = re.compile(
        r"https?://(?:www\.)?(?:x|twitter)\.com/"
        r"(?P<username>[^/]+)/status/(?P<status_id>\d+)"
    )

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, str) and bool(cls._pattern.match(value))

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        url = str(value)
        try:
            html = await self._fetch_browser_html(url)
            extraction_mode = "playwright"
        except Exception:
            html = await fetch_html(url)
            extraction_mode = "metadata_fallback"
        soup = BeautifulSoup(html, "lxml")
        title = self._meta(soup, "og:title") or "X Post"
        description = self._meta(soup, "og:description") or ""
        author = title.split(" on X", 1)[0].strip() if " on X" in title else None

        match = self._pattern.match(url)
        target_path = (
            f"/{match.group('username')}/status/{match.group('status_id')}".lower()
            if match
            else ""
        )
        article_nodes = soup.select("main article") or soup.select("article")
        target_index = self._target_article_index(article_nodes, target_path)
        context_nodes = (
            article_nodes[: target_index + 1]
            if target_index is not None
            else article_nodes[:1]
        )
        articles = await self._hydrate_parent_context(context_nodes, url)
        text = self._format_context(articles) or description

        if target_index is not None:
            article_title = context_nodes[-1].select_one("h1")
            if article_title and article_title.get_text(strip=True):
                title = article_title.get_text(" ", strip=True)

        image_urls = [
            node.get("src")
            for node in soup.select(
                'main article img[src*="pbs.twimg.com/media"], meta[property="og:image"]'
            )
            if node.get("src")
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
            author=author,
            raw_content=text,
            media_files=media_files,
            metadata={
                "context_posts": len(articles),
                "has_parent_context": len(articles) > 1,
                "extraction_mode": extraction_mode,
            },
        )

    async def _fetch_browser_html(self, url: str) -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = None
            if self.config.playwright_user_data_dir:
                context = await playwright.chromium.launch_persistent_context(
                    str(self.config.playwright_user_data_dir),
                    headless=True,
                    locale="zh-CN",
                )
            else:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(locale="zh-CN")
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.locator("main article").first.wait_for(
                    state="visible", timeout=30_000
                )
                # X renders long-form article bodies after the post shell appears.
                await page.wait_for_timeout(1_500)
                await self._expand_x_article(page, url)
                return await page.content()
            finally:
                await context.close()
                if browser:
                    await browser.close()

    async def _expand_x_article(self, page, url: str) -> None:
        match = self._pattern.match(url)
        if not match:
            return
        status_id = match.group("status_id")
        target = page.locator(
            f'main article:has(a[href*="/status/{status_id}"])'
        ).first
        if await target.count() == 0:
            return

        heading = target.locator("h1").first
        if await heading.count() == 0:
            return
        preview_text = (await target.inner_text()).strip()
        paragraph_count = await target.locator("p").count()
        has_cover = await target.locator('img[alt="Article cover image"]').count() > 0
        if not self._needs_article_expansion(
            preview_text, paragraph_count, has_cover
        ):
            return

        try:
            await heading.click(timeout=5_000)
        except Exception:
            return

        minimum_length = max(1_000, len(preview_text) + 500)
        for _ in range(20):
            await page.wait_for_timeout(500)
            expanded_text = (await target.inner_text()).strip()
            if (
                len(expanded_text) >= minimum_length
                or await target.locator("p").count() >= 4
            ):
                return

    @staticmethod
    def _needs_article_expansion(
        text: str, paragraph_count: int, has_cover: bool
    ) -> bool:
        return len(text) < 1_500 and (has_cover or paragraph_count < 3)

    async def _hydrate_parent_context(self, context_nodes: list, url: str) -> list[str]:
        articles: list[str] = []
        for node in context_nodes[:-1]:
            text = node.get_text("\n", strip=True)
            parent_path = self._first_status_path(node)
            if parent_path:
                try:
                    parent_html = await self._fetch_browser_html(
                        f"{urlparse(url).scheme}://{urlparse(url).netloc}{parent_path}"
                    )
                    parent_soup = BeautifulSoup(parent_html, "lxml")
                    parent_nodes = (
                        parent_soup.select("main article")
                        or parent_soup.select("article")
                    )
                    parent_index = self._target_article_index(
                        parent_nodes, parent_path.lower()
                    )
                    if parent_index is not None:
                        text = parent_nodes[parent_index].get_text("\n", strip=True)
                except Exception:
                    pass
            articles.append(text)
        if context_nodes:
            articles.append(context_nodes[-1].get_text("\n", strip=True))
        return articles

    @staticmethod
    def _first_status_path(node) -> str | None:
        for link in node.select("a[href]"):
            path = urlparse(str(link.get("href"))).path.rstrip("/")
            if re.fullmatch(r"/[^/]+/status/\d+", path):
                return path
        return None

    @staticmethod
    def _target_article_index(article_nodes: list, target_path: str) -> int | None:
        if not target_path:
            return None
        for index, node in enumerate(article_nodes):
            paths = {
                urlparse(str(link.get("href"))).path.rstrip("/").lower()
                for link in node.select("a[href]")
            }
            if target_path in paths:
                return index
        return None

    @staticmethod
    def _format_context(articles: list[str]) -> str:
        cleaned = [text.strip() for text in articles if text.strip()]
        if not cleaned:
            return ""
        parts = [
            f"## 上文 {index + 1}\n\n{text}"
            for index, text in enumerate(cleaned[:-1])
        ]
        parts.append(
            "## 当前帖子（其内嵌文字包含引用推文或 X Article 正文）"
            f"\n\n{cleaned[-1]}"
        )
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _meta(soup: BeautifulSoup, property_name: str) -> str | None:
        node = soup.select_one(f'meta[property="{property_name}"]')
        return str(node.get("content")).strip() if node and node.get("content") else None
