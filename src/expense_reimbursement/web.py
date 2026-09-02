"""Web 上传界面：上传票据图片，自动生成 A5 报销单与凭证 PDF。"""

from __future__ import annotations

import base64
import json as _json
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


def _llm_recognize(image_path: Path) -> dict[str, Any] | None:
    """调用 OpenRouter 视觉模型识别凭证；失败返回 None。"""

    import os as _os
    from pathlib import Path as _P

    env_file = _P(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                _os.environ.setdefault(k.strip(), v.strip())

    key = _os.environ.get("DEEPSEEK_API_KEY", "")
    model = _os.environ.get("DEEPSEEK_MODEL", "deepseek/deepseek-v4-flash-vision-exp")
    base = _os.environ.get("DEEPSEEK_BASE_URL", "https://openrouter.ai/api/v1")
    if not key:
        return None
    try:
        import openai
    except ImportError:
        return None

    data = base64.b64encode(image_path.read_bytes()).decode()
    prompt = (
        "这是报销凭证/转账/账单详情截图。忽略顶部状态栏(时间、信号、电量)和无关UI，"
        "重点看「转账备注」「商品名称」「金额」等核心字段。只返回 JSON，字段："
        "project(报销项目，从 [软件服务费,货款,交通费,住宿费,餐饮费,办公费,差旅费,通讯费,其他费用]"
        "中选，"
        "转账备注写「货款」则 project=货款)，"
        "subject(报销事由一句中文，用转账备注或商品名，如「支付货款」「OPENROUTER API 充值」)，"
        "remarks(备注，照抄转账备注/重要信息，含货币/入账)，"
        "amount(数字金额，不带¥)，date(YYYY-MM-DD)，merchant(对方/商户名称)。"
    )
    for _attempt in range(3):
        try:
            client = openai.OpenAI(api_key=key, base_url=base, timeout=120)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data}},
                ]}],
                max_tokens=600,
            )
            txt = (resp.choices[0].message.content or "").strip()
            s, e = txt.find("{"), txt.rfind("}")
            if s == -1 or e <= s:
                continue  # 空响应，重试
            obj = _json.loads(txt[s : e + 1])
            if isinstance(obj, dict) and obj:
                return obj
        except Exception:
            continue
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
    """上传图片后优先用视觉大模型识别，失败回退 OCR+规则，返回建议供前端回填。"""

    file = request.files.get("receipt")
    if not file or not file.filename:
        return {"error": "请选择票据图片。"}, 400
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return {"error": "不支持的图片格式，请上传 jpg/png/bmp/webp 等图片。"}, 400

    stem = Path(file.filename).stem.replace(" ", "_") or "preview"
    tmp_path = OUTPUT_DIR / f"{stem}_{_unix_ts()}{ext}"
    file.save(tmp_path)

    project = subject = remarks = ""
    merchant = tax_id = ""
    amount = "0"
    date_str = ""

    # 1) 先试视觉大模型
    llm = _llm_recognize(tmp_path)
    if llm:
        project = _map_project(str(llm.get("project") or ""))
        subject = str(llm.get("subject") or "")
        remarks = str(llm.get("remarks") or "")
        merchant = str(llm.get("merchant") or "")
        amount = str(llm.get("amount") or "0")
        date_str = str(llm.get("date") or "")
        text = str(llm.get("subject") or "")
    else:
        # 2) 回退 OCR + 规则
        try:
            engine = get_engine()
            text = engine.extract_text(tmp_path)
        except Exception as exc:
            return {"error": f"OCR 识别失败：{exc}. 请确认已安装 Tesseract OCR 及中文包。"}, 500
        item, info = parse_receipt_text(text)
        ai = summarize(text, info.merchant, item.amount)
        project = _map_project(ai.get("project") or "")
        subject = ai.get("subject") or ""
        remarks = ai.get("remarks") or ""
        merchant = info.merchant
        amount = str(item.amount)
        date_str = item.date.isoformat() if item.date else ""

    return {
        "project": project,
        "subject": subject,
        "remarks": remarks,
        "merchant": merchant,
        "tax_id": tax_id,
        "amount": amount,
        "date": date_str,
        "pages": 1,
        "img": tmp_path.name,
        "extracted_text": text,
    }


def _map_project(key: str) -> str:
    mapping = {
        "software-service": "软件服务费", "software": "软件服务费",
        "transport": "交通费", "accommodation": "住宿费", "meal": "餐饮费",
        "office": "办公费", "travel": "差旅费", "communication": "通讯费",
        "other": "其他费用",
        "软件服务费": "软件服务费", "交通费": "交通费", "住宿费": "住宿费",
        "餐饮费": "餐饮费", "办公费": "办公费", "差旅费": "差旅费",
        "通讯费": "通讯费", "其他费用": "其他费用",
        "货款": "货款", "贷款": "货款", "采购款": "货款", "设备款": "货款",
        "服务费": "服务费", "订阅": "软件服务费",
    }
    k = (key or "").strip().lower()
    if k in mapping:
        return mapping[k]
    # 常见中文费用词直接透传
    if k.endswith("费") or "款" in k:
        return key.strip()
    return "其他费用"


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
    if len(rows) > 8:
        return render_template(
            "index.html",
            payments=_payments(),
            error="一张报销单最多支持 8 条明细，请分批提交。",
        )

    # 用 rows 里的 img（已保存的凭证图路径）确定凭证图列表
    images: list[Path] = []
    for row in rows:
        img_name = row.get("img") or ""
        if img_name:
            img_path = OUTPUT_DIR / img_name
            if img_path.exists():
                images.append(img_path)
    # 兜底：若 rows 没带 img，回退到前端上传的文件
    if not images:
        for f in files:
            if not f or not f.filename:
                continue
            ext = Path(f.filename).suffix.lower()
            if ext not in ALLOWED_EXT:
                continue
            stem = Path(f.filename).stem.replace(" ", "_") or "receipt"
            ip = OUTPUT_DIR / f"{stem}_{_unix_ts()}{ext}"
            f.save(ip)
            images.append(ip)

    applicant = (request.form.get("applicant") or "").strip()
    department = (request.form.get("department") or "").strip()
    reimburser = (request.form.get("reimburser") or "").strip()
    supervisor = (request.form.get("supervisor") or "").strip()
    reviewer = (request.form.get("reviewer") or "").strip()
    cashier = (request.form.get("cashier") or "").strip()
    date_value = _parse_date(request.form.get("date"))
    remarks = (request.form.get("remarks") or "").strip()
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
            remarks=remarks,
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
        merchant="、".join((row.get("subject") or "") for row in rows),
        total=str(total),
        capital=r.subject,
        item_count=r.item_count,
        reimb_info={
            "applicant": r.applicant,
            "department": r.department,
            "subject": "、".join((row.get("subject") or "") for row in rows),
            "payment_method": r.payment_method.value,
            "remarks": remarks,
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
