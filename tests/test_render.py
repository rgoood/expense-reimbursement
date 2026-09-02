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
