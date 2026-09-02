"""从 OCR 文本中抽取报销字段的规则解析器。"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from expense_reimbursement.models import Category, ExpenseItem, ReceiptInfo

AMOUNT_RE = re.compile(
    r"(?P<currency>[¥￥$]|RMB|USD)?\s*"
    r"(?P<amount>\d[\d,]*\.\d{1,2})",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(?P<year>20\d{2})\s*[年/\-.]\s*"
    r"(?P<month>\d{1,2})\s*[月/\-.]\s*"
    r"(?P<day>\d{1,2})\s*[日号]?"
)
TAX_ID_RE = re.compile(r"\b[A-Z0-9]{18}\b", re.IGNORECASE)
ORDER_NO_RE = re.compile(
    r"(?i)(?:订单号|单号|invoice no\.?|order no\.?)\s*[:：]?\s*([A-Za-z0-9\-]{4,})"
)


CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.TRANSPORT: ("地铁", "公交", "出租车", "滴滴", "打车", "加油", "高铁", "机票", "停车"),
    Category.MEAL: ("餐饮", "饭", "餐厅", "咖啡", "早餐", "午餐", "晚餐", "外卖", "茶", "奶茶"),
    Category.ACCOMMODATION: ("酒店", "住宿", "宾馆", "旅馆", "民宿"),
    Category.OFFICE: ("办公", "文具", "打印", "耗材", "办公用品", "书"),
    Category.TRAVEL: ("差旅", "旅行", "机票", "酒店", "租车"),
    Category.COMMUNICATION: ("话费", "通讯", "电话", "宽带", "流量"),
}


def _parse_amount(text: str) -> Decimal | None:
    """提取文本中第一个金额。"""

    match = AMOUNT_RE.search(text)
    if not match:
        return None
    raw = match.group("amount").replace(",", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    currency = (match.group("currency") or "").upper()
    if currency in {"USD", "$"}:
        return value
    # ¥ / ￥ / RMB / 无符号视为人民币，保留两位小数
    return value.quantize(Decimal("0.01"))


def _parse_date(text: str) -> date | None:
    """提取文本中第一个日期。"""

    match = DATE_RE.search(text)
    if not match:
        return None
    year, month, day = (int(match.group(k)) for k in ("year", "month", "day"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _categorize(text: str) -> Category:
    """根据关键词判断类目。"""

    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                return category
    return Category.OTHER


def _extract_merchant(text: str) -> str:
    """抽取商户/公司名（优先独立行，其次行内中文词组）。"""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    skip_prefixes = ("收款", "付款", "纳税人", "订单", "金额", "日期", "单号", "发票", "备注")
    # 优先：不含金额、不含日期关键词且不以字段名前缀开头的行
    candidates = [
        line
        for line in lines
        if not AMOUNT_RE.search(line)
        and "年" not in line
        and "月" not in line
        and "日" not in line
        and not any(line.startswith(prefix) for prefix in skip_prefixes)
        and len(line) >= 2
    ]
    if candidates:
        return candidates[0]
    # 兜底：抽取行内第一个连续中文词组作为商户名
    cn_pattern = re.compile(r"[一-龥]{2,12}")
    for line in lines:
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        match = cn_pattern.search(line)
        if match and "年" not in match.group(0) and "月" not in match.group(0):
            return match.group(0)
    return ""


def parse_receipt_text(text: str) -> tuple[ExpenseItem, ReceiptInfo]:
    """把 OCR 文本解析成一条费用明细与凭证信息。"""

    amount = _parse_amount(text) or Decimal("0")
    item_date = _parse_date(text)
    tax_id_match = TAX_ID_RE.search(text)
    order_match = ORDER_NO_RE.search(text)

    item = ExpenseItem(
        description=text[:60].replace("\n", " ").strip(),
        amount=amount,
        category=_categorize(text),
        date=item_date,
    )
    receipt = ReceiptInfo(
        merchant=_extract_merchant(text),
        tax_id=tax_id_match.group(0) if tax_id_match else "",
        order_no=order_match.group(1) if order_match else "",
        notes=text,
    )
    return item, receipt


def build_from_sampling(text: str) -> tuple[ExpenseItem, ReceiptInfo]:
    """兼容入口：把样本文本转换为数据（用于 demo）。"""

    return parse_receipt_text(text)
