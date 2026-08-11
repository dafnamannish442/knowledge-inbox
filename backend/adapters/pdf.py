from __future__ import annotations

import asyncio
from pathlib import Path

from pypdf import PdfReader

from backend.adapters.base import FetchedContent, SourceAdapter


class PDFAdapter(SourceAdapter):
    source_type = "pdf"

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, Path) and value.suffix.lower() == ".pdf"

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        return await asyncio.to_thread(self._fetch_sync, Path(value), kwargs.get("title"))

    def _fetch_sync(self, path: Path, title: object = None) -> FetchedContent:
        reader = PdfReader(path)
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        text = "\n\n".join(f"## 第 {index} 页\n\n{page}" for index, page in enumerate(pages, 1))
        ocr_used = False
        page_images: list[str] = []
        if len(text.strip()) < max(80, len(reader.pages) * 20):
            ocr_text, page_images = self._ocr(path)
            if ocr_text:
                text = ocr_text
                ocr_used = True
        metadata = reader.metadata or {}
        return FetchedContent(
            source_type=self.source_type,
            title=str(title or metadata.get("/Title") or path.stem),
            author=metadata.get("/Author"),
            raw_content=text,
            media_files=[str(path), *page_images],
            metadata={"pages": len(reader.pages), "ocr_used": ocr_used},
        )

    def _ocr(self, path: Path) -> tuple[str, list[str]]:
        try:
            import fitz
            import pytesseract
            from PIL import Image
        except ImportError:
            return "", []

        image_dir = self.config.data_dir / "derived" / path.stem
        image_dir.mkdir(parents=True, exist_ok=True)
        texts: list[str] = []
        images: list[str] = []
        with fitz.open(path) as document:
            for index, page in enumerate(document):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image_path = image_dir / f"page-{index + 1}.png"
                pixmap.save(image_path)
                images.append(str(image_path))
                page_text = pytesseract.image_to_string(Image.open(image_path), lang="chi_sim+eng")
                texts.append(f"## 第 {index + 1} 页\n\n{page_text.strip()}")
        return "\n\n".join(texts), images
