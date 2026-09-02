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


def test_extract_merchant_from_seller_label() -> None:
    text = (
        "增值税电子普通发票\n"
        "购买方名称: 某某科技有限公司\n"
        "销售方名称: 广州白云国际酒店有限公司\n"
        "金额: 1280.50"
    )
    _, receipt = parse_receipt_text(text)
    assert receipt.merchant == "广州白云国际酒店有限公司"


def test_extract_description_from_item_label() -> None:
    text = "项目名称: 差旅住宿费\n金额: ￥1280.50"
    item, _ = parse_receipt_text(text)
    assert item.description == "差旅住宿费"


def test_extract_merchant_skips_title() -> None:
    text = "增值税电子普通发票\n购买方名称: 深圳某某公司\n开票日期: 2026年9月1日\n金额 100.00"
    _, receipt = parse_receipt_text(text)
    assert receipt.merchant in {"深圳某某公司", ""}


def test_invoice_category_hotel() -> None:
    text = "差旅住宿费\n金额: ￥1280.50\n日期: 2026年09月02日"
    item, _ = parse_receipt_text(text)
    assert item.category == Category.ACCOMMODATION
