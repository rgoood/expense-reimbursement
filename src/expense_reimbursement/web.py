"""Web 上传界面：上传票据图片，自动生成 A5 报销单与凭证 PDF。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, send_from_directory, url_for

from expense_reimbursement.ai_summary import summarize
from expense_reimbursement.models import PaymentMethod
from expense_reimbursement.ocr import get_engine
from expense_reimbursement.parser import parse_receipt_text
from expense_reimbursement.service import process_receipts

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


def _parse_date(value: str | None) -> date | None:
    """解析 YYYY-MM-DD 日期字符串，失败返回 None。"""

    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


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





@app.post("/preview")
def preview() -> Any:
    """上传图片后即时 OCR 识别，返回建议的项目/事由/备注等，供前端回填。"""

    file = request.files.get("receipt")
    if not file or not file.filename:
        return {"error": "请选择票据图片。"}, 400
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return {"error": "不支持的图片格式，请上传 jpg/png/bmp/webp 等图片。"}, 400

    # 保存临时文件
    stem = Path(file.filename).stem.replace(" ", "_") or "preview"
    tmp_path = OUTPUT_DIR / f"{stem}_{_unix_ts()}{ext}"
    file.save(tmp_path)

    try:
        engine = get_engine()
        text = engine.extract_text(tmp_path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"OCR 识别失败：{exc}. 请确认本机已安装 Tesseract OCR 及中文语言包。"}, 500

    item, receipt_info = parse_receipt_text(text)
    ai = summarize(text, receipt_info.merchant, item.amount)
    date_str = item.date.isoformat() if item.date else ""

    return {
        "project": ai["project"],
        "subject": ai["subject"],
        "remarks": ai["remarks"],
        "merchant": receipt_info.merchant,
        "tax_id": receipt_info.tax_id,
        "amount": str(item.amount),
        "date": date_str,
        "pages": 1,
        "extracted_text": text,
    }


@app.post("/process")
def process() -> Any:
    """接收多张凭证 + 每行明细，生成一张多明细报销单与多页凭证。"""

    files = request.files.getlist("receipts")
    if not files:
        return render_template("index.html", payments=_payments(), error="请选择票据图片。")

    # 解析前端提交的行明细（JSON）
    import json as _json
    rows_raw = request.form.get("rows")
    try:
        rows = _json.loads(rows_raw) if rows_raw else []
    except Exception:
        rows = []
    if not rows:
        rows = [{} for _ in files]

    # 保存所有上传图
    images: list[Path] = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        stem = Path(f.filename).stem.replace(" ", "_") or "receipt"
        img_path = OUTPUT_DIR / f"{stem}_{_unix_ts()}{ext}"
        f.save(img_path)
        images.append(img_path)

    applicant = (request.form.get("applicant") or "").strip()
    department = (request.form.get("department") or "").strip()
    reimburser = (request.form.get("reimburser") or "").strip()
    supervisor = (request.form.get("supervisor") or "").strip()
    reviewer = (request.form.get("reviewer") or "").strip()
    cashier = (request.form.get("cashier") or "").strip()
    date_value = _parse_date(request.form.get("date"))
    pm_raw = (request.form.get("payment_method") or "其他").strip()
    try:
        payment_method = PaymentMethod(pm_raw)
    except ValueError:
        payment_method = PaymentMethod.OTHER

    try:
        result = process_receipts(
            rows,
            images,
            OUTPUT_DIR,
            applicant=applicant,
            department=department,
            reimburser=reimburser,
            payment_method=payment_method,
            date=date_value,
            accounting_supervisor=supervisor,
            reviewer=reviewer,
            cashier=cashier,
        )
    except Exception as exc:  # noqa: BLE001
        return render_template(
            "index.html",
            payments=_payments(),
            error=f"处理失败：{exc}. 请确认本机已安装 Tesseract OCR 及中文语言包。",
        )

    r = result.reimbursement
    total = sum((item.amount for item in r.items), Decimal("0"))
    return render_template(
        "result.html",
        form_name=result.form_path.name,
        receipt_name=result.receipt_path.name,
        form_url=url_for("download", filename=result.form_path.name),
        receipt_url=url_for("download", filename=result.receipt_path.name),
        extracted_text="",
        merchant="、".join((row.get("subject") or "") for row in rows),
        tax_id="",
        order_no="",
        total=str(total),
        capital=r.subject,
        item_count=r.item_count,
        reimb_info={
            "applicant": r.applicant,
            "department": r.department,
            "subject": "、".join((row.get("subject") or "") for row in rows),
            "payment_method": r.payment_method.value,
            "remarks": "",
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
