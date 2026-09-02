"""OCR 引擎抽象与默认 Tesseract 适配器。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Engine(Protocol):
    """把图片文件变成文本的引擎。"""

    def extract_text(self, image_path: Path) -> str:
        """从图片中提取纯文本。"""
        ...


_WINDOWS_CANDIDATES = (
    Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
    Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
)


def _find_tesseract() -> str:
    """定位 tesseract 可执行文件（标准路径优先，其次 PATH）。"""

    for candidate in _WINDOWS_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("tesseract")
    if found:
        return found
    raise RuntimeError("未找到 tesseract，请先安装 Tesseract OCR。")


def _find_tessdata() -> Path:
    """定位含 chi_sim 的 tessdata 目录（用户目录优先，其次系统目录）。"""

    user_dir = Path.home() / ".tessdata"
    if (user_dir / "chi_sim.traineddata").exists():
        return user_dir
    sys_dir = Path("C:/Program Files/Tesseract-OCR/tessdata")
    if (sys_dir / "chi_sim.traineddata").exists():
        return sys_dir
    return user_dir


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

        pytesseract.pytesseract.tesseract_cmd = _find_tesseract()
        tessdata = _find_tessdata()
        config = f"--tessdata-dir {tessdata}"

        with Image.open(image_path) as image:
            text = pytesseract.image_to_string(
                image, lang=self.language, config=config
            )
            return str(text).strip()


def get_engine() -> Engine:
    """返回默认 OCR 引擎。"""

    return TesseractEngine()
