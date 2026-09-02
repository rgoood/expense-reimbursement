"""AI 摘要生成：根据 OCR 文本推断报销项目、报销事由、备注。

这是无外部 LLM 时的规则引擎基线；配置 API Key 后可替换为真正的 LLM。
一切输出都是「建议」，用户在 Web 页面上可修改。
"""

from __future__ import annotations

from decimal import Decimal

from expense_reimbursement.models import Category, ReceiptInfo

# 商户/关键词 -> 报销项目
PROJECT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("openrouter", "openai", "aws", "阿里云", "腾讯云", "微软",
      "google", "api", "软件", "订阅"), "软件服务费"),
    (("酒店", "住宿", "宾馆", "旅馆", "民宿", "民宿"), "住宿费"),
    (("滴滴", "出行", "打车", "出租车", "高铁", "火车",
      "机票", "加油", "停车", "地铁", "公交"), "交通费"),
    (("餐饮", "饭", "餐厅", "咖啡", "外卖", "奶茶", "午餐", "晚餐", "早餐"), "餐饮费"),
    (("办公", "文具", "打印", "耗材", "采购"), "办公费"),
    (("话费", "通讯", "宽带", "电话", "流量", "中国移动", "中国联通", "电信"), "通讯费"),
    (("快递", "物流", "邮政", "顺丰", "圆通"), "快递费"),
    (("广告", "推广", "营销", "百度", "抖音", "小红书"), "推广费"),
]

# 商户/关键词 -> 事由后缀
SUBJECT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("openrouter", "openai", "api", "aws", "云", "软件", "订阅"), "API 充值"),
    (("酒店", "住宿", "宾馆", "民宿"), "住宿报销"),
    (("滴滴", "出行", "打车", "出租"), "出行费用"),
    (("高铁", "火车", "机票", "航空"), "差旅车费"),
    (("加油", "油", "停车"), "车辆费用"),
    (("餐饮", "饭", "餐厅", "咖啡", "外卖", "奶茶"), "餐饮费用"),
    (("办公", "文具", "打印"), "办公采购"),
    (("话费", "通讯", "宽带", "流量"), "通讯费用"),
    (("快递", "物流", "邮政"), "快递费用"),
]


def _guess_project(text: str) -> str:
    lowered = text.lower()
    for keywords, label in PROJECT_RULES:
        if any(k in lowered for k in keywords):
            return label
    return "其他费用"


def _guess_subject(text: str, merchant: str) -> str:
    lowered = text.lower()
    for keywords, tail in SUBJECT_RULES:
        if any(k in lowered for k in keywords):
            return f"{merchant or '相关'} {tail}"
    # 兜底：商户名（若含非空）+ 费用
    if merchant:
        return f"{merchant} 相关费用"
    return "费用报销"


def _guess_remarks(text: str) -> str:
    """根据 OCR 文本推断备注（货币、入账等）。"""

    lowered = text.lower()
    has_usd = ("美元" in text) or ("usd" in lowered) or ("$" in text)
    has_rmb = ("人民币" in text) or ("rmb" in lowered) or ("¥" in text) or ("￥" in text)
    has_installment = "入账" in text or "分期" in text
    parts: list[str] = []
    if has_usd and has_rmb:
        parts.append("美元消费，人民币入账，按银行账单金额报销")
    elif has_usd:
        parts.append("美元消费，按账单金额报销")
    elif has_installment:
        parts.append("按银行账单入账金额报销")
    return "；".join(parts) + "。" if parts else ""


def summarize(text: str, merchant: str = "", amount: Decimal = Decimal("0")) -> dict[str, str]:
    """返回建议的 {project, subject, remarks}。"""

    return {
        "project": _guess_project(text),
        "subject": _guess_subject(text, merchant),
        "remarks": _guess_remarks(text),
    }


def summarize_item(
    text: str, receipt_info: ReceiptInfo, amount: Decimal
) -> dict[str, str]:
    """从 OCR 文本 + 识别信息生成建议摘要。"""

    merchant = receipt_info.merchant or ""
    return summarize(text, merchant, amount)


def category_to_project(category: Category) -> str:
    """把循环类目映射为报销项目名。"""

    mapping = {
        Category.TRANSPORT: "交通费",
        Category.MEAL: "餐饮费",
        Category.ACCOMMODATION: "住宿费",
        Category.OFFICE: "办公费",
        Category.TRAVEL: "差旅费",
        Category.COMMUNICATION: "通讯费",
        Category.OTHER: "其他费用",
    }
    return mapping.get(category, "其他费用")
