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


def _is_noise_line(line: str) -> bool:
    """判断是否为手机状态栏/UI 杂讯行（非凭证业务内容）。"""

    import re as _re
    if not line:
        return True
    # 状态栏时间
    if _re.match(r"^\d{1,2}:\d{2}$", line):
        return True
    # 纯符号/无意义英文（如 OQ tu > Eb），长度短且基本无字母正文
    no_text = _re.sub(r"[^A-Za-z0-9\u4e00-\u9fa5]", "", line)
    if len(no_text) <= 2:
        return True
    # UI 文案
    ui_words = ("交易详情", "已入账", "我要分期", "对此交易有疑问", "消费", "退款", "支付")
    if line in ui_words:
        return True
    return False


def _extract_txn_merchant(text: str) -> str:
    """从交易摘要行提取商户，如 '(消费) OPENROUTER, INC'。"""

    txn_pattern = re.compile(
        r"[（(]\s*(?:消费|退款|支付|转账)\s*[)）]\s*([A-Za-z0-9][A-Za-z0-9.,&\-\s]{1,30})"
    )
    for line in text.splitlines():
        match = txn_pattern.search(line.strip())
        if match:
            return match.group(1).strip()
    return ""


def _extract_merchant(text: str) -> str:
    """抽取商户/公司名（交易摘要 > 收票主体 > 购方 > 独立行 > 中文词组）。"""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # 0) 交易摘要优先（手机银行/支付截图常见）
    txn = _extract_txn_merchant(text)
    if txn:
        return txn
    # 1) 优先销售方/收款方/商户等收票主体
    seller_pattern = re.compile(
        r"(?:销售方名称|收款方名称|收款方|收款单位|商户名称|商户|付款方名称|公司名称)\s*[:：]?\s*([^\s:：]{2,30})"
    )
    for line in lines:
        match = seller_pattern.search(line)
        if match:
            return match.group(1).strip()
    # 2) 其次购买方名称
    buyer_pattern = re.compile(r"(?:购买方名称|购买方)\s*[:：]?\s*([^\s:：]{2,30})")
    for line in lines:
        match = buyer_pattern.search(line)
        if match:
            return match.group(1).strip()
    # 3) 排除发票/收据标题行与字段行、状态栏杂讯
    title_words = (
        "增值税", "电子发票", "普通发票", "专用发票", "收据", "小票", "发票号码", "发票代码"
    )
    skip_prefixes = (
        "收款", "付款", "纳税人", "订单", "金额", "日期", "单号", "代码", "备注", "合计",
        "价税", "购买方", "销售方", "交易日期", "交易金额", "入账", "交易卡号",
    )
    candidates = [
        line
        for line in lines
        if not AMOUNT_RE.search(line)
        and "年" not in line
        and "月" not in line
        and "日" not in line
        and not any(word in line for word in title_words)
        and not any(line.startswith(prefix) for prefix in skip_prefixes)
        and not _is_noise_line(line)
        and len(line) >= 2
    ]
    if candidates:
        return candidates[0]
    # 4) 兜底：抽取第一个连续中文词组
    cn_pattern = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9.,&\-]{2,30}")
    for line in lines:
        if any(word in line for word in title_words):
            continue
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        match = cn_pattern.search(line)
        if match and "年" not in match.group(0) and "月" not in match.group(0):
            return match.group(0)
    return ""


def _extract_description(text: str) -> str:
    """抽取费用项目/摘要描述（优先字段名，其次商户名，最后截断）。"""

    field_pattern = re.compile(
        r"(?:项目名称|商品名称|货物名称|服务名称|摘要|费用项目|内容)\s*[:：]?\s*([^\s:：]{2,20})"
    )
    for line in text.splitlines():
        match = field_pattern.search(line.strip())
        if match:
            return match.group(1).strip()
    merchant = _extract_merchant(text)
    if merchant:
        return merchant
    normalized = text.replace("\n", " ").strip()
    return normalized[:20]


def parse_receipt_text(text: str) -> tuple[ExpenseItem, ReceiptInfo]:
    """把 OCR 文本解析成一条费用明细与凭证信息。"""

    amount = _parse_amount(text) or Decimal("0")
    item_date = _parse_date(text)
    tax_id_match = TAX_ID_RE.search(text)
    order_match = ORDER_NO_RE.search(text)

    item = ExpenseItem(
        description=_extract_description(text),
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
