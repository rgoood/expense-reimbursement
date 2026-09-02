"""Web 上传界面：上传票据图片，自动生成 A5 报销单与凭证 PDF。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, send_from_directory, url_for

from expense_reimbursement.models import PaymentMethod
from expense_reimbursement.service import process_receipt

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = STATIC_DIR / "outputs"
TEMPLATE_DIR = BASE_DIR / "templates"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".gif"}


def _payments() -> list[str]:
    return [pm.value for pm in PaymentMethod]


def _dec(value: str | None) -> Decimal:
    value = (value or "").strip()
    if not value:
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0")


def _int(value: str | None, default: int = 1) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@app.get("/")
def index() -> str:
    return render_template("index.html", payments=_payments())


@app.post("/process")
def process() -> Any:
    # 安全校验扩展名
    file = request.files.get("receipt")
    if not file or not file.filename:
        return render_template(
            "index.html",
            payments=_payments(),
            error="请选择票据图片。",
        )
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return render_template(
            "index.html",
            payments=_payments(),
            error="不支持的图片格式，请上传 jpg/png/bmp/webp 等图片。",
        )

    # 表单字段（黑色可填值）
    applicant = (request.form.get("applicant") or "").strip()
    department = (request.form.get("department") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    remarks = (request.form.get("remarks") or "").strip()
    project = (request.form.get("project") or "").strip()
    payment_raw = (request.form.get("payment_method") or "其他").strip()
    payment_method = PaymentMethod(payment_raw)
    pages = _int(request.form.get("pages"), 1)
    reimburser = (request.form.get("reimburser") or "").strip()
    supervisor = (request.form.get("supervisor") or "").strip()
    reviewer = (request.form.get("reviewer") or "").strip()
    cashier = (request.form.get("cashier") or "").strip()
    loan = _dec(request.form.get("original_loan"))
    refund = _dec(request.form.get("refund"))

    # 保存上传的图片到唯一文件名
    stem = Path(file.filename).stem.replace(" ", "_") or "receipt"
    upload_path = OUTPUT_DIR / f"{stem}_{_unix_ts()}{ext}"
    file.save(upload_path)

    try:
        result = process_receipt(
            upload_path,
            OUTPUT_DIR,
            applicant=applicant,
            department=department,
            subject=subject,
            payment_method=payment_method,
            remarks=remarks,
            attachment_pages=pages,
            project=project,
            reimburser=reimburser,
            accounting_supervisor=supervisor,
            reviewer=reviewer,
            cashier=cashier,
            original_loan=loan,
            refund=refund,
        )
    except Exception as exc:  # noqa: BLE001 - 前端需要看到错误信息
        return render_template(
            "index.html",
            payments=_payments(),
            error=f"处理失败：{exc}. 请确认本机已安装 Tesseract OCR 及中文语言包。",
        )

    form_name = result.form_path.name
    receipt_name = result.receipt_path.name
    r = result.reimbursement
    return render_template(
        "result.html",
        form_name=form_name,
        receipt_name=receipt_name,
        form_url=url_for("download", filename=form_name),
        receipt_url=url_for("download", filename=receipt_name),
        extracted_text=result.extracted_text,
        merchant=result.receipt_info.merchant,
        tax_id=result.receipt_info.tax_id,
        order_no=result.receipt_info.order_no,
        total=str(r.total),
        capital=r.subject,
        item_count=r.item_count,
        reimb_info={
            "applicant": r.applicant,
            "department": r.department,
            "subject": r.subject,
            "payment_method": r.payment_method.value,
            "remarks": r.remarks,
            "reimburser": r.reimburser,
            "attachment_pages": r.attachment_pages,
        },
    )


@app.get("/download/<path:filename>")
def download(filename: str) -> Any:
    return send_from_directory(str(OUTPUT_DIR), filename, as_attachment=False)


def _unix_ts() -> int:
    import time

    return int(time.time() * 1000)


if __name__ == "__main__":  # pragma: no cover
    app.run(host="127.0.0.1", port=5000, debug=True)
