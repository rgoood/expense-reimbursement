"""OCR 引擎抽象与默认 Tesseract 适配器。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Engine(Protocol):
    """把图片文件变成文本的引擎。"""

    def extract_text(self, image_path: Path) -> str:
        """从图片中提取纯文本。"""
        ...


class TesseractEngine:
    """基于 Tesseract OCR 的实现（依赖 pytesseract 与本机 tesseract）。"""

    def __init__(self, language: str = "chi_sim+eng") -> None:
        self.language = language

    def extract_text(self, image_path: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "OCR 需要安装 pytesseract 与 Pillow：pip install -e '.[ocr]'"
            ) from exc

        with Image.open(image_path) as image:
            text = pytesseract.image_to_string(image, lang=self.language)
            return str(text).strip()


def get_engine() -> Engine:
    """返回默认 OCR 引擎。"""

    return TesseractEngine()