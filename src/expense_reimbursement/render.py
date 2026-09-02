"""生成 A5 横向财务报销单 PDF（参照企业报销单模板）。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A5
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from expense_reimbursement.models import Reimbursement

# A5 横向：594.0 x 419.5 pt (210 x 148 mm)
PAGE_W, PAGE_H = A5[1], A5[0]
FONT = "KaiTi"
FONT_PATH = "C:/Windows/Fonts/simkai.ttf"
FALLBACK_FONT = "STSong-Light"
BLUE = (0.04, 0.32, 0.6)

# 模板列坐标（pt，页面从顶部数起，绘制时用 ty 转换）
LEFT = 13.2
X_PROJECT_R = 66.0
X_SUMMARY_R = 311.8
X_AMOUNT_R = 452.1
RIGHT = 582.9
# 金额分列：9 个子列，从 X_AMOUNT 到 X_NOTE
X_AMOUNT = 325.4
AMOUNT_COL_W = 15.5
# 模板行坐标（页顶向下）
Y_TITLE = 117.6
Y_HEADER = 134.1
Y_SUBHEADER = 145.2
Y_ROW0 = 156.3
ROW_H = 16.0
Y_TOTAL = 284.3
Y_CAPITAL = 302.4
Y_SIGN = 318.9

AMOUNT_UNITS = ["百", "千", "万", "千", "百", "十", "元", "角", "分"]


def ty(y_top: float) -> float:
    """把模板的'从页顶向下'坐标转换为 ReportLab 左下原点坐标。"""

    return PAGE_H - y_top


def _register_font() -> None:
    """注册楷体字体；找不到系统楷体则回退到内置 CID 宋体。"""

    global FONT
    try:
        pdfmetrics.getFont(FONT)
        return
    except KeyError:
        pass
    try:
        pdfmetrics.registerFont(TTFont(FONT, FONT_PATH))
        pdfmetrics.getFont(FONT)
    except Exception:
        FONT = FALLBACK_FONT
        try:
            pdfmetrics.getFont(FONT)
        except KeyError:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont

            pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _split_amount_digits(value: Decimal) -> list[str]:
    """把金额拆成 9 个位置字符（百万/十万/万/千/百/十/元/角/分，从高到低）。"""

    v = abs(Decimal(str(value)))
    integer = int(v)
    cents = int((v - integer) * 100 + Decimal("0.001"))
    jiao, fen = cents // 10, cents % 10
    int_str = f"{integer:07d}"[-7:]  # 7 位整数：百万 十万 万 千 百 十 元
    cells = [int_str[i] for i in range(7)]
    cells.append(str(jiao))
    cells.append(str(fen))
    return cells


def _capital_text(value: Decimal) -> str:
    """返回中文大写金额字符串。"""

    from expense_reimbursement.models import amount_to_chinese

    return amount_to_chinese(value)


def _amount_cx(i: int) -> float:
    """返回金额分列第 i 列的中心 x 坐标。"""

    return X_AMOUNT + AMOUNT_COL_W * i + AMOUNT_COL_W / 2


def _text(
    c: canvas.Canvas, x: float, y: float, s: str, size: float = 7.7,
    color: tuple[float, float, float] = BLUE, align: str = "left",
) -> None:
    _register_font()
    c.setFont(FONT, size)
    c.setFillColor(color)
    if align == "center":
        c.drawCentredString(x, y, s)
    elif align == "right":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def _line(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float,
          w: float = 0.75) -> None:
    c.setStrokeColor(BLUE)
    c.setLineWidth(w)
    c.line(x1, ty(y1), x2, ty(y2))


def _rect(c: canvas.Canvas, x: float, y: float, w: float, h: float,
          yfrom_bottom: bool = False) -> None:
    c.setStrokeColor(BLUE)
    c.setLineWidth(0.75)
    if yfrom_bottom:
        c.rect(x, y, w, h)
    else:
        c.rect(x, ty(y + h), w, h)


def _fit(text: str, max_w: float, size: float) -> str:
    """按宽度截断文本。"""

    if pdfmetrics.stringWidth(text, FONT, size) <= max_w:
        return text
    out = ""
    for ch in text:
        if pdfmetrics.stringWidth(out + ch, FONT, size) > max_w:
            return out + "..."
        out += ch
    return out


def render_reimbursement_form(r: Reimbursement, output_path: Path) -> Path:
    """生成 A5 横向财务报销单。"""

    _register_font()
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))

    # 标题
    _text(c, PAGE_W / 2, ty(Y_TITLE + 10), "费   用   报   销   单", 15.4, BLUE, "center")

    # 表头行：报销部门 / 年 月 日 / 单据及附件
    _text(c, LEFT, ty(Y_HEADER), "报销部门：" + (r.department or ""), 6.6)
    _text(c, 239, ty(Y_HEADER), r.created_at.strftime("%Y年%m月%d日"), 6.6)
    pages = str(r.attachment_pages)
    if 1 <= r.attachment_pages <= 9:
        pages = "壹贰叁肆伍陆柒捌玖"[r.attachment_pages - 1]
    _text(c, 453.7, ty(Y_HEADER), f"单据及附件共 {pages} 页", 6.6)

    # 表格外框
    c.setStrokeColor(BLUE)
    c.setLineWidth(0.75)
    c.rect(LEFT, ty(Y_TOTAL), RIGHT - LEFT, Y_TOTAL - Y_SUBHEADER)

    # 明细表头
    hdr_y = ty(Y_SUBHEADER + 4)
    _text(c, (LEFT + X_PROJECT_R) / 2, hdr_y, "报销项目", 7.7, BLUE, "center")
    _text(c, (X_PROJECT_R + X_SUMMARY_R) / 2, hdr_y, "摘要", 7.7, BLUE, "center")
    _text(c, (X_SUMMARY_R + X_AMOUNT_R) / 2, hdr_y, "金额", 7.7, BLUE, "center")
    _text(c, (X_AMOUNT_R + RIGHT) / 2, hdr_y, "备 注", 7.7, BLUE, "center")

    # 金额分列表头
    for i, unit in enumerate(AMOUNT_UNITS):
        _text(c, _amount_cx(i), ty(Y_SUBHEADER - 3), unit, 5.6, BLUE, "center")

    # 竖分隔线
    for x in (X_PROJECT_R, X_SUMMARY_R, X_AMOUNT_R, RIGHT):
        _line(c, x, Y_SUBHEADER, x, Y_TOTAL)
    for i in range(9):
        cx = X_AMOUNT + AMOUNT_COL_W * i
        _line(c, cx, Y_SUBHEADER, cx, Y_TOTAL)

    # 明细行
    y = Y_ROW0
    for item in r.items:
        ry = ty(y)
        _text(c, LEFT + 6, ry, _fit(item.project or "", X_PROJECT_R - LEFT - 10, 6.6), 6.6)
        desc_w = X_SUMMARY_R - X_PROJECT_R - 12
        _text(c, X_PROJECT_R + 6, ry, _fit(item.description or "", desc_w, 6.6), 6.6)
        digits = _split_amount_digits(item.amount)
        for i, dg in enumerate(digits):
            if dg != "0":
                _text(c, _amount_cx(i), ry, dg, 6.6, BLUE, "center")
        _text(c, X_AMOUNT_R + 6, ry, _fit(item.remarks or "", RIGHT - X_AMOUNT_R - 10, 6.6), 6.6)
        _line(c, LEFT, y, RIGHT, y)
        y += ROW_H

    # 合计行
    total_y = ty(Y_TOTAL + 2)
    _text(c, (X_PROJECT_R + X_SUMMARY_R) / 2, total_y, "合计", 6.6, BLUE, "center")
    for i, dg in enumerate(_split_amount_digits(r.total)):
        if dg != "0":
            _text(c, _amount_cx(i), total_y, dg, 6.6, BLUE, "center")

    # 金额大写 + 原借款/应退款
    cap_y = ty(Y_CAPITAL + 2)
    _text(c, LEFT + 6, cap_y, "金额（大写）：", 6.6)
    _text(c, LEFT + 50, cap_y, _capital_text(r.total), 7.7)
    _text(c, 322, cap_y, f"原借款：{r.original_loan} 元", 6.6)
    _text(c, 451, cap_y, f"应退（补）款：{r.refund} 元", 6.6)

    # 签字栏
    sign_y = ty(Y_SIGN + 2)
    _text(c, LEFT + 6, sign_y, "会计主管：" + (r.accounting_supervisor or ""), 7.7)
    _text(c, 124, sign_y, "复核：" + (r.reviewer or ""), 7.7)
    _text(c, 318, sign_y, "出纳：" + (r.cashier or ""), 7.7)
    _text(c, 448, sign_y, "报销人：" + (r.reimburser or r.applicant or ""), 7.7)

    c.showPage()
    c.save()
    return output_path


def render_receipt(
    image_path: Path | None, output_path: Path, summary: str = ""
) -> Path:
    """生成 A5 横向凭证 PDF。"""

    _register_font()
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))
    _text(c, PAGE_W / 2, PAGE_H - 40, "报销凭证", 14, BLUE, "center")
    if image_path and Path(image_path).exists():
        from PIL import Image
        with Image.open(image_path) as img:
            iw, ih = img.size
        maxw, maxh = PAGE_W - 40, PAGE_H - 140
        ratio = min(maxw / iw, maxh / ih)
        dw, dh = iw * ratio, ih * ratio
        c.drawImage(str(image_path), 20, 50, width=dw, height=dh, preserveAspectRatio=True)
        if summary:
            _text(c, PAGE_W / 2, 40, "识别摘要：" + summary, 8, BLUE, "center")
    else:
        _text(c, PAGE_W / 2, PAGE_H / 2, "（未提供凭证图片。）", 9, BLUE, "center")
    c.showPage()
    c.save()
    return output_path
