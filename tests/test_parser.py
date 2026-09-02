"""文本解析层测试。"""

from decimal import Decimal

from expense_reimbursement.models import Category
from expense_reimbursement.parser import parse_receipt_text


def test_parse_amount_and_date() -> None:
    text = "滴滴出行 2026年9月1日 金额：￥156.80"
    item, receipt = parse_receipt_text(text)
    assert item.amount == Decimal("156.80")
    assert item.category == Category.TRANSPORT
    assert item.date is not None and item.date.isoformat() == "2026-09-01"
    assert receipt.merchant == "滴滴出行"


def test_parse_meal_category() -> None:
    item, _ = parse_receipt_text("午餐 美团外卖 金额 88.00")
    assert item.category == Category.MEAL


def test_parse_usd_amount() -> None:
    item, _ = parse_receipt_text("Taxi $12.50")
    assert item.amount == Decimal("12.50")


def test_parse_tax_id() -> None:
    tax_id = "91310000MA1K4XYZ1A"
    item, receipt = parse_receipt_text(f"发票 税号 {tax_id} 金额 100.00")
    assert receipt.tax_id == tax_id


def test_no_amount_defaults_zero() -> None:
    item, _ = parse_receipt_text("没有金额的凭证")
    assert item.amount == Decimal("0")
