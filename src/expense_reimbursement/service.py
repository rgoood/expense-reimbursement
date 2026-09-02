"""端到端流程编排：凭证图片 -> A5 报销单 PDF + 凭证 PDF。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from expense_reimbursement.models import (
    Category,
    ExpenseItem,
    PaymentMethod,
    ReceiptInfo,
    Reimbursement,
)
from expense_reimbursement.ocr import Engine, get_engine
from expense_reimbursement.parser import parse_receipt_text
from expense_reimbursement.render import render_receipt, render_reimbursement_form


@dataclass(slots=True)
class ReceiptResult:
    """处理结果：两张 PDF 路径与提取的信息。"""

    form_path: Path
    receipt_path: Path
    reimbursement: Reimbursement
    receipt_info: ReceiptInfo
    extracted_text: str


def process_receipt(
    image_path: Path,
    output_dir: Path,
    *,
    engine: Engine | None = None,
    applicant: str = "",
    department: str = "",
    subject: str = "",
    payment_method: PaymentMethod = PaymentMethod.OTHER,
    remarks: str = "",
) -> ReceiptResult:
    """处理一张凭证并输出两张 A5 PDF。"""

    image_path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ocr_engine = engine or get_engine()
    text = ocr_engine.extract_text(image_path)
    item, receipt_info = parse_receipt_text(text)

    reimbursement = Reimbursement(
        applicant=applicant,
        department=department,
        subject=subject or receipt_info.merchant,
        payment_method=payment_method,
        items=[item],
        remarks=remarks,
        created_at=datetime.now(),
    )

    stem = image_path.stem
    form_path = output_dir / f"{stem}_reimbursement_form.pdf"
    receipt_path = output_dir / f"{stem}_receipt.pdf"

    render_reimbursement_form(reimbursement, form_path)
    render_receipt(image_path, receipt_path, summary=receipt_info.merchant)

    return ReceiptResult(
        form_path=form_path,
        receipt_path=receipt_path,
        reimbursement=reimbursement,
        receipt_info=receipt_info,
        extracted_text=text,
    )


def sample_reimbursement() -> Reimbursement:
    """构建一个内置样例报销单（用于 demo，无需 OCR）。"""

    item = ExpenseItem(
        description="滴滴出行-客户拜访",
        amount=Decimal("156.80"),
        category=Category.TRANSPORT,
        date=date(2026, 9, 1),
    )
    item2 = ExpenseItem(
        description="午餐-商务宴请",
        amount=Decimal("320.00"),
        category=Category.MEAL,
        date=date(2026, 9, 1),
    )
    return Reimbursement(
        applicant="张三",
        department="市场部",
        subject="客户拜访差旅报销",
        payment_method=PaymentMethod.ALIPAY,
        items=[item, item2],
        remarks="已按规定提交凭证。",
    )
