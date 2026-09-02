"""命令行入口。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from expense_reimbursement.models import PaymentMethod
from expense_reimbursement.render import render_receipt, render_reimbursement_form
from expense_reimbursement.service import process_receipt, sample_reimbursement


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense-reimbursement",
        description="上传报销凭证，自动识别并生成 A5 报销单与凭证 PDF。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="生成示例 A5 报销单与凭证 PDF，无需 OCR。")
    demo.add_argument(
        "--output", type=Path, default=Path("output"), help="输出目录，默认 output/。"
    )
    demo.add_argument("--applicant", default="张三", help="申请人。")

    proc = sub.add_parser("process", help="处理一张凭证图片，OCR 并生成 A5 PDF。")
    proc.add_argument("image", type=Path, help="凭证图片路径。")
    proc.add_argument("--output", type=Path, default=Path("output"), help="输出目录。")
    proc.add_argument("--applicant", default="", help="申请人。")
    proc.add_argument("--department", default="", help="部门。")
    proc.add_argument("--subject", default="", help="报销事由。")
    proc.add_argument(
        "--payment",
        default="其他",
        choices=[pm.value for pm in PaymentMethod],
        help="支付方式。",
    )
    proc.add_argument("--remarks", default="", help="备注。")
    return parser


def app(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口。"""

    args = _build_parser().parse_args(argv)

    if args.command == "demo":
        reimbursement = sample_reimbursement()
        output = args.output
        output.mkdir(parents=True, exist_ok=True)
        form_path = render_reimbursement_form(reimbursement, output / "reimbursement_form.pdf")
        # 生成一张占位凭证图片
        sample_img = output / "sample_receipt.png"
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (800, 500), "white")
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, 790, 490], outline="black", width=3)
            draw.text((40, 40), "Demo Receipt 123456", fill="black")
            draw.text((40, 80), "Amount: 156.80", fill="black")
            img.save(sample_img)
        except ImportError:
            sample_img = None
        receipt_path = render_receipt(sample_img, output / "receipt.pdf", summary="示例凭证")
        print(f"已生成报销单：{form_path}")
        print(f"已生成凭证：{receipt_path}")
        return 0

    if args.command == "process":
        if not args.image.exists():
            print(f"错误：找不到图片 {args.image}", file=sys.stderr)
            return 2
        payment = PaymentMethod(args.payment)
        result = process_receipt(
            args.image,
            args.output,
            applicant=args.applicant,
            department=args.department,
            subject=args.subject,
            payment_method=payment,
            remarks=args.remarks,
        )
        print(f"识别文本：{result.extracted_text[:120]}")
        print(f"报销单：{result.form_path}")
        print(f"凭证：{result.receipt_path}")
        print(f"合计：¥{result.reimbursement.total}")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(app())
