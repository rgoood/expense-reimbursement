"""智能报销单生成工具：凭证图片 -> A5 报销单 PDF + A5 凭证 PDF + Web 界面。"""

from typing import Any

from expense_reimbursement.models import (
    Category,
    ExpenseItem,
    PaymentMethod,
    ReceiptInfo,
    Reimbursement,
)
from expense_reimbursement.service import process_receipt

__all__ = [
    "Category",
    "ExpenseItem",
    "PaymentMethod",
    "ReceiptInfo",
    "Reimbursement",
    "process_receipt",
    "create_app",
    "run_web",
]

__version__ = "0.2.1"


def create_app() -> Any:
    """创建 Flask 应用（延迟导入，避免未装 Flask 时报错）。"""

    from expense_reimbursement.web import app

    return app


def run_web(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """启动 Web 上传界面。"""

    from expense_reimbursement.web import app

    app.run(host=host, port=port, debug=debug)
