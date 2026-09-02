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


def test_amount_to_chinese() -> None:
    from expense_reimbursement.models import amount_to_chinese

    assert amount_to_chinese(Decimal("2000")) == "贰仟元整"
    assert amount_to_chinese(Decimal("711.40")) == "柒佰壹拾壹元肆角"
    assert amount_to_chinese(Decimal("100.05")) == "壹佰元零伍分"
    assert amount_to_chinese(Decimal("0")) == "零元整"
