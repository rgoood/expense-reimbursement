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

    description: str = ""
    amount: Decimal = Decimal("0")
    category: Category = Category.OTHER
    date: date | None = None

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("金额不能为负数")
        if self.amount != self.amount.quantize(Decimal("0.01")):
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

    @property
    def total(self) -> Decimal:
        """合计金额。"""

        return sum((item.amount for item in self.items), Decimal("0"))

    @property
    def item_count(self) -> int:
        """条目数。"""

        return len(self.items)
