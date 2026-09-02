"""模型层基础测试。"""

from decimal import Decimal

import pytest

from expense_reimbursement.models import Category, ExpenseItem, PaymentMethod, Reimbursement


def test_expense_item_negative_amount() -> None:
    with pytest.raises(ValueError):
        ExpenseItem(amount=Decimal("-1"))


def test_expense_item_rounds_to_two_decimals() -> None:
    item = ExpenseItem(amount=Decimal("123.456"))
    assert item.amount == Decimal("123.46")


def test_reimbursement_total() -> None:
    r = Reimbursement(
        applicant="张三",
        items=[
            ExpenseItem(description="a", amount=Decimal("10.00")),
            ExpenseItem(description="b", amount=Decimal("20.50")),
        ],
    )
    assert r.total == Decimal("30.50")
    assert r.item_count == 2


def test_payment_method_value() -> None:
    assert PaymentMethod.ALIPAY.value == "支付宝"


def test_category_value() -> None:
    assert Category.MEAL.value == "餐饮"
