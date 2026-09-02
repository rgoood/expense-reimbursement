"""领域模型：报销单与凭证的核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class PaymentMethod(str, Enum):
    """支付方式。"""

    CASH = "现金"
    BANK_TRANSFER = "银行转账"
    ALIPAY = "支付宝"
    WECHAT = "微信"
    CREDIT_CARD = "信用卡"
    OTHER = "其他"


class Category(str, Enum):
    """费用类目。"""

    TRANSPORT = "交通"
    MEAL = "餐饮"
    ACCOMMODATION = "住宿"
    OFFICE = "办公"
    TRAVEL = "差旅"
    COMMUNICATION = "通讯"
    OTHER = "其他"


@dataclass(slots=True)
class ExpenseItem:
    """一条费用明细。"""

    project: str = ""
    description: str = ""
    amount: Decimal = Decimal("0")
    category: Category = Category.OTHER
    date: date | None = None
    remarks: str = ""

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("金额不能为负数")
        self.amount = self.amount.quantize(Decimal("0.01"))


@dataclass(slots=True)
class ReceiptInfo:
    """凭证信息。"""

    merchant: str = ""
    tax_id: str = ""
    order_no: str = ""
    notes: str = ""


@dataclass(slots=True)
class Reimbursement:
    """一份报销单。"""

    applicant: str = ""
    department: str = ""
    subject: str = ""
    payment_method: PaymentMethod = PaymentMethod.OTHER
    items: list[ExpenseItem] = field(default_factory=list)
    remarks: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    # 财务报销单模板字段
    attachment_pages: int = 1          # 单据及附件共__页
    original_loan: Decimal = Decimal("0")  # 原借款
    refund: Decimal = Decimal("0")     # 应退（补）款
    accounting_supervisor: str = ""    # 会计主管
    reviewer: str = ""                 # 复核
    cashier: str = ""                  # 出纳
    reimburser: str = ""               # 报销人

    @property
    def total(self) -> Decimal:
        """合计金额。"""

        return sum((item.amount for item in self.items), Decimal("0"))

    @property
    def item_count(self) -> int:
        """条目数。"""

        return len(self.items)


CN_DIGITS = "零壹贰叁肆伍陆柒捌玖"
CN_UNITS = ["", "拾", "佰", "仟"]
CN_GROUPS = ["", "万", "亿", "兆"]


def amount_to_chinese(value: float | Decimal) -> str:
    """把数字金额转换为财务大写（不含货币单位），如 2000 -> 贰仟元整。"""

    value = Decimal(str(value))
    if value == 0:
        return "零元整"
    negative = value < 0
    value = abs(value)
    integer = int(value)
    cents = int((value - integer) * 100 + Decimal("0.001"))
    yuan_str = _int_to_chinese(integer)
    if cents == 0:
        result = f"{yuan_str}元整"
    else:
        jiao = cents // 10
        fen = cents % 10
        result = yuan_str + "元"
        if jiao:
            result += CN_DIGITS[jiao] + "角"
        elif fen:
            result += "零"
        if fen:
            result += CN_DIGITS[fen] + "分"
    if negative:
        return "负" + result
    return result


def _int_to_chinese(num: int) -> str:
    if num == 0:
        return "零"
    sections = []
    group = 0
    while num > 0:
        chunk = num % 10000
        if chunk:
            s = _four_digits(chunk)
            sections.append(s + CN_GROUPS[group])
        else:
            sections.append("")
        num //= 10000
        group += 1
    result = ""
    for part in reversed(sections):
        if part:
            if result and not result.endswith("零"):
                result += "零"
            result += part
    return result or "零"


def _four_digits(num: int) -> str:
    chars: list[str] = []
    zero_pending = False
    for i in range(3, -1, -1):
        digit = (num // (10 ** i)) % 10
        if digit == 0:
            if chars:
                zero_pending = True
        else:
            if zero_pending:
                chars.append("零")
                zero_pending = False
            chars.append(CN_DIGITS[digit])
            if i > 0:
                chars.append(CN_UNITS[i])
    return "".join(chars)
