"""生成 A5 规格的报销单与凭证 PDF。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from reportlab.lib.pagesizes import A5
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from expense_reimbursement.models import Reimbursement

A5_W, A5_H = A5
MARGIN = 20
FONT = "STSong-Light"


def _register_font() -> None:
    """注册中文字体（ReportLab 内置 CID 字体，无需外部文件）。"""

    try:
        pdfmetrics.getFont(FONT)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _a5_canvas(output_path: Path) -> canvas.Canvas:
    """创建 A5 页面画布。"""

    _register_font()
    return canvas.Canvas(str(output_path), pagesize=A5)


def _wrap_text(text: str, max_width: float, font_size: float) -> list[str]:
    """极简按字符宽度拆行（中英文混合）。"""

    width = pdfmetrics.stringWidth
    lines: list[str] = []
    current = ""
    for char in text:
        if width(current + char, FONT, font_size) > max_width and current:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def _draw_table(
    c: canvas.Canvas,
    x: float,
    y: float,
    col_widths: Sequence[float],
    rows: list[list[str]],
    font_size: float = 9,
    row_height: float = 18,
) -> float:
    """绘制简单表格，返回结束的 y 坐标。"""

    x_pos = x
    for i, row in enumerate(rows):
        y_pos = y - i * row_height
        x_cursor = x_pos
        for col, col_w in zip(row, col_widths, strict=False):
            c.setFont(FONT, font_size)
            c.drawString(x_cursor + 4, y_pos + 6, col)
            c.rect(x_cursor, y_pos, col_w, row_height)
            x_cursor += col_w
    return y - len(rows) * row_height


def render_reimbursement_form(
    reimbursement: Reimbursement,
    output_path: Path,
) -> Path:
    """生成 A5 报销单 PDF。"""

    c = _a5_canvas(output_path)
    _register_font()
    c.setFont(FONT, 16)
    c.drawCentredString(A5_W / 2, A5_H - 40, "费用报销单")
    c.setFont(FONT, 9)
    created = reimbursement.created_at.strftime("%Y-%m-%d")
    c.drawCentredString(A5_W / 2, A5_H - 56, "报销日期：" + created)

    # 基本信息
    c.setFont(FONT, 10)
    info_y = A5_H - 80
    c.drawString(MARGIN, info_y, f"申请人：{reimbursement.applicant or '________________'}")
    c.drawString(A5_W / 2, info_y, f"部门：{reimbursement.department or '________________'}")
    subject = reimbursement.subject or "____________________"
    c.drawString(MARGIN, info_y - 18, f"报销事由：{subject}")
    c.drawString(A5_W / 2, info_y - 18, f"支付方式：{reimbursement.payment_method.value}")

    # 明细表
    c.setFont(FONT, 10)
    c.drawString(MARGIN, info_y - 42, "费用明细")
    table_y = info_y - 60
    col_widths = [24.0, 46.0, 22.0, 36.0]
    header = ["序号", "内容", "日期", "金额"]
    table_y -= 18
    rows: list[list[str]] = [header]
    for i, item in enumerate(reimbursement.items, start=1):
        rows.append(
            [
                str(i),
                item.description or "—",
                item.date.strftime("%Y-%m-%d") if item.date else "—",
                str(item.amount),
            ]
        )
    table_y = _draw_table(c, MARGIN, table_y, col_widths, rows)

    # 合计
    total_y = table_y - 24
    c.setFont(FONT, 11)
    c.drawString(MARGIN, total_y, f"合计金额：¥{reimbursement.total}")
    c.drawString(A5_W / 2, total_y, f"共 {reimbursement.item_count} 笔")

    # 备注
    note_y = total_y - 28
    c.setFont(FONT, 9)
    c.drawString(MARGIN, note_y, f"备注：{reimbursement.remarks or ''}")

    # 签字栏
    sign_y = 40
    c.setFont(FONT, 9)
    c.drawString(MARGIN, sign_y, "申请人签字：")
    c.drawString(MARGIN + 70, sign_y, "______________")
    c.drawString(A5_W / 2, sign_y, "审批人签字：")
    c.drawString(A5_W / 2 + 80, sign_y, "______________")

    c.showPage()
    c.save()
    return output_path


def render_receipt(
    image_path: Path | None,
    output_path: Path,
    summary: str = "",
) -> Path:
    """生成 A5 凭证 PDF（嵌入凭证图片 + 识别摘要）。"""

    c = _a5_canvas(output_path)
    _register_font()
    c.setFont(FONT, 14)
    c.drawCentredString(A5_W / 2, A5_H - 40, "报销凭证")

    if image_path and image_path.exists():
        from PIL import Image

        with Image.open(image_path) as img:
            img_w, img_h = img.size
        max_w = A5_W - 2 * MARGIN
        max_h = A5_H - 140
        ratio = min(max_w / img_w, max_h / img_h)
        draw_w = img_w * ratio
        draw_h = img_h * ratio
        c.drawImage(
            str(image_path), MARGIN, 60, width=draw_w, height=draw_h, preserveAspectRatio=True
        )
        if summary:
            c.setFont(FONT, 9)
            c.drawCentredString(A5_W / 2, 40, "识别摘要：" + summary)
    else:
        c.setFont(FONT, 10)
        c.drawString(MARGIN, A5_H / 2, "（未提供凭证图片，仅生成单据。）")

    c.showPage()
    c.save()
    return output_path
