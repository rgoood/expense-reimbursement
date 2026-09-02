"""PDF 渲染层测试（不依赖外部字体/OCR）。"""

from decimal import Decimal
from pathlib import Path

from expense_reimbursement.models import Category, ExpenseItem, Reimbursement
from expense_reimbursement.render import render_reimbursement_form


def test_render_form_creates_pdf(tmp_path: Path) -> None:
    r = Reimbursement(
        applicant="张三",
        items=[
            ExpenseItem(description="打车", amount=Decimal("50.00"), category=Category.TRANSPORT)
        ],
    )
    out = tmp_path / "form.pdf"
    result = render_reimbursement_form(r, out)
    assert result.exists()
    assert result.stat().st_size > 0
    assert result.read_bytes()[:5] == b"%PDF-"


def test_a5_landscape_size(tmp_path: Path) -> None:
    """报销单应为 A5 横向（210 x 148 mm）。"""

    from decimal import Decimal as D
    r = Reimbursement(applicant="张三", items=[ExpenseItem(description="打车", amount=D("50.00"))])
    out = tmp_path / "landscape.pdf"
    render_reimbursement_form(r, out)
    from pypdf import PdfReader

    page = PdfReader(str(out)).pages[0]
    width_mm = float(page.mediabox.width) / 72 * 25.4
    height_mm = float(page.mediabox.height) / 72 * 25.4
    assert round(width_mm, 0) == 210
    assert round(height_mm, 0) == 148
    assert width_mm > height_mm  # 横向


def test_split_amount_digits() -> None:
    from expense_reimbursement.render import _split_amount_digits

    assert _split_amount_digits(Decimal("2000")) == ["0", "0", "0", "2", "0", "0", "0", "0", "0"]
    assert _split_amount_digits(Decimal("711.40")) == ["0", "0", "0", "0", "7", "1", "1", "4", "0"]
    assert _split_amount_digits(Decimal("12.34")) == ["0", "0", "0", "0", "0", "1", "2", "3", "4"]


def test_font_fallback_to_cid_when_kaiti_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """系统无楷体时应回退到内置 CID 宋体，仍能生成 PDF。"""

    import expense_reimbursement.render as render_mod

    monkeypatch.setattr(render_mod, "FONT_PATH", "C:/no/such/kaiti.ttf")
    monkeypatch.setattr(render_mod, "FONT", "KaiTi")
    r = Reimbursement(
        applicant="张三", items=[ExpenseItem(description="打车", amount=Decimal("50.00"))]
    )
    out = tmp_path / "fallback.pdf"
    render_reimbursement_form(r, out)
    assert out.exists()
    assert out.stat().st_size > 0
