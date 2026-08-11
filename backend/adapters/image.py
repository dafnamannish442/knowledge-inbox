from __future__ import annotations

import asyncio
from pathlib import Path

from backend.adapters.base import FetchedContent, SourceAdapter


class ImageAdapter(SourceAdapter):
    source_type = "image"
    _suffixes = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".tiff", ".bmp"}

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        return isinstance(value, Path) and value.suffix.lower() in cls._suffixes

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        path = Path(value)
        text = await asyncio.to_thread(self._ocr, path)
        return FetchedContent(
            source_type=self.source_type,
            title=str(kwargs.get("title") or path.stem),
            raw_content=text,
            media_files=[str(path)],
            metadata={"ocr_used": bool(text)},
        )

    @staticmethod
    def _ocr(path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image

            return pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng").strip()
        except ImportError:
            return ""
