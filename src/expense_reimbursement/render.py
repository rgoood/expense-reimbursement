"""生成 A5 横向财务报销单 PDF（精确复刻企业报销单模板）。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A5
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from expense_reimbursement.models import Reimbursement

# A5 横向：595 x 420 pt
PAGE_W, PAGE_H = A5[1], A5[0]
FONT = "KaiTi"
FONT_PATH = "C:/Windows/Fonts/simkai.ttf"
FALLBACK_FONT = "STSong-Light"
BLUE = (0.04, 0.32, 0.6)


def ty(y_top: float) -> float:
    """把模板的"从页顶向下"坐标转换为 ReportLab 左下原点坐标。"""

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
            pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _split_amount_digits(value: Decimal) -> list[str]:
    """把金额拆成 9 个位置字符（百万/十万/万/千/百/十/元/角/分，从高到低）。"""

    v = abs(Decimal(str(value)))
    integer = int(v)
    cents = int((v - integer) * 100 + Decimal("0.001"))
    jiao, fen = cents // 10, cents % 10
    int_str = f"{integer:07d}"[-7:]
    cells = [int_str[i] for i in range(7)]
    cells.append(str(jiao))
    cells.append(str(fen))
    return cells


def _capital_text(value: Decimal) -> str:
    """返回中文大写金额字符串。"""

    from expense_reimbursement.models import amount_to_chinese

    return amount_to_chinese(value)


# 模板列坐标（pt，页顶 x）
LX = 13.5          # 左边界
X_PROJ_R = 118.3   # 报销项目右
X_SUMM_R = 311.6   # 摘要右 / 金额左
X_AMT_L = 312.0
X_AMT_R = 434.8    # 金额右 / 备注左
X_NOTE_R = 452.1   # 备注右 / 领导审批左
RX = 583.1         # 右边界

# 金额 9 分列右边界（312 -> 434.8）
AMT_COLS = [325.4, 339.1, 352.8, 366.4, 380.0, 393.6, 407.3, 421.0, 434.6]
AMT_UNITS = ["百", "千", "万", "千", "百", "十", "元", "角", "分"]

# 模板行坐标（页顶 y）
Y_TITLE = 101.3
Y_UNDERLINE = 117.0
Y_TOP = 134.1       # 表头顶
Y_HDR = 145.2       # 表头下（金额列标签上）
Y_ROW0 = 156.3      # 第一行数据顶
ROW_H = 16.0        # 行距（156.3,172.3,188.3,204.3,220.3,236.3,252.3,268.4）
Y_TOTAL = 284.3     # 合计行
Y_CAP = 302.0       # 金额大写顶
Y_SIGN = 319.0      # 签字栏

# 模板文字 bbox 顶部 y（用于基线对齐，size*0.8 偏移）
TXT_MULT = 0.82


def _amt_cx(i: int) -> float:
    """金额分列第 i 列中心 x。"""

    left = X_AMT_L if i == 0 else AMT_COLS[i - 1]
    return (left + AMT_COLS[i]) / 2


def _text(
    c: canvas.Canvas,
    x: float,
    y_top: float,
    s: str,
    size: float = 7.7,
    color: tuple[float, float, float] = BLUE,
    align: str = "left",
) -> None:
    """在 y_top（页顶 bbox 顶部）处绘制文字。"""

    _register_font()
    c.setFont(FONT, size)
    c.setFillColor(color)
    baseline = PAGE_H - (y_top + size * TXT_MULT)
    if align == "center":
        c.drawCentredString(x, baseline, s)
    elif align == "right":
        c.drawRightString(x, baseline, s)
    else:
        c.drawString(x, baseline, s)


def _line(
    c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float, w: float = 0.6
) -> None:
    c.setStrokeColor(BLUE)
    c.setLineWidth(w)
    c.line(x1, ty(y1), x2, ty(y2))



def _print_amount_split(
    c: canvas.Canvas, digits: list[str], y: float
) -> None:
    """按模板样式打印金额分列：从首个非0开始显示，跳过前导0。"""

    # 找第一个非0索引
    start = 0
    while start < len(digits) - 1 and digits[start] == "0":
        start += 1
    for i in range(start, len(digits)):
        _text(c, _amt_cx(i), y, digits[i], 6.6, BLUE, "center")


def _fit(text: str, max_w: float, size: float) -> str:
    if pdfmetrics.stringWidth(text, FONT, size) <= max_w:
        return text
    out = ""
    for ch in text:
        if pdfmetrics.stringWidth(out + ch, FONT, size) > max_w:
            return out + "..."
        out += ch
    return out


def render_reimbursement_form(r: Reimbursement, output_path: Path) -> Path:
    """生成 A5 横向财务报销单（复刻模板版式）。"""

    _register_font()
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))
    c.setLineWidth(0.6)
    c.setStrokeColor(BLUE)

    # ---- 标题 ----
    _text(c, PAGE_W / 2, Y_TITLE, "费   用   报   销   单", 15.4, BLUE, "center")
    _line(c, 144.8, Y_UNDERLINE, 380.1, Y_UNDERLINE, 1.0)

    # ---- 表头信息行 ----
    _text(c, LX + 1, Y_TOP + 5, "报销部门：" + (r.department or ""), 6.6)
    _text(c, 239, Y_TOP + 5, r.created_at.strftime("%Y年%m月%d日"), 6.6)
    pages_cn = "壹贰叁肆伍陆柒捌玖"[r.attachment_pages - 1]
    if not (1 <= r.attachment_pages <= 9):
        pages_cn = str(r.attachment_pages)
    _text(c, 453.7, Y_TOP + 5, f"单据及附件共 {pages_cn} 页", 6.6)

    # ---- 表格外框 ----
    c.rect(LX, ty(Y_CAP + 4.8), RX - LX, (Y_CAP + 4.8) - Y_TOP)

    # ---- 列表头 ----
    _text(c, (LX + X_PROJ_R) / 2, Y_HDR + 1, "报销项目", 7.7, BLUE, "center")
    _text(c, (X_PROJ_R + X_SUMM_R) / 2, Y_HDR + 1, "摘要", 7.7, BLUE, "center")
    _text(c, (X_AMT_L + X_AMT_R) / 2, Y_TOP + 2, "金额", 7.7, BLUE, "center")
    # 竖排备注
    _text(c, (X_AMT_R + X_NOTE_R) / 2, Y_HDR + 4, "备", 7.7, BLUE, "center")
    _text(c, (X_AMT_R + X_NOTE_R) / 2, Y_HDR + 30, "注", 7.7, BLUE, "center")
    # 竖排领导审批
    for k, ch in enumerate("领导审批"):
        _text(c, (X_NOTE_R + RX) / 2, 225 + k * 10, ch, 7.7, BLUE, "center")

    # ---- 金额分列表头 ----
    for i, unit in enumerate(AMT_UNITS):
        _text(c, _amt_cx(i), Y_HDR + 3, unit, 5.6, BLUE, "center")

    # ---- 金额分列边框 ----
    c.rect(X_AMT_L, ty(Y_TOTAL), X_AMT_R - X_AMT_L, Y_TOTAL - Y_HDR)
    for x in AMT_COLS:
        _line(c, x, Y_HDR, x, Y_TOTAL)

    # ---- 明细行 ----
    for row_idx, item in enumerate(r.items):
        y = Y_ROW0 + row_idx * ROW_H
        _text(c, LX + 4, y, _fit(item.project or "", X_PROJ_R - LX - 8, 6.6), 6.6)
        _text(c, X_PROJ_R + 4, y, _fit(item.description or "", X_SUMM_R - X_PROJ_R - 8, 6.6), 6.6)
        _print_amount_split(c, _split_amount_digits(item.amount), y)
        _text(c, X_AMT_R + 3, y, _fit(item.remarks or "", RX - X_AMT_R - 6, 6.6), 6.6)

    # ---- 明细行线 ----
    y = Y_ROW0
    for _ in range(8):
        _line(c, LX, y, X_AMT_R, y)
        if y + ROW_H >= Y_TOTAL:
            break
        y += ROW_H
    # 明细区竖线
    for x in (X_PROJ_R, X_SUMM_R, X_NOTE_R, RX):
        _line(c, x, Y_HDR, x, Y_TOTAL)
    _line(c, X_AMT_R, Y_HDR, X_AMT_R, Y_TOTAL)

    # ---- 合计行 ----
    _line(c, LX, Y_TOTAL, RX, Y_TOTAL)
    _text(c, (X_PROJ_R + X_SUMM_R) / 2, Y_TOTAL + 5, "合计", 6.6, BLUE, "center")
    _print_amount_split(c, _split_amount_digits(r.total), Y_TOTAL + 5)

    # ---- 金额大写区 ----
    _line(c, LX, Y_CAP, RX, Y_CAP)
    _text(c, LX + 10, Y_CAP - 5, "金额", 7.7, BLUE)
    _text(c, LX + 6, Y_CAP + 3, "（大写）", 7.7, BLUE)
    _text(c, 67, Y_CAP - 2, "佰 仟 万 仟 佰 拾 元 角 分", 7.7, BLUE)
    cap = _capital_text(r.total)
    _text(c, 67, Y_CAP + 5, cap, 8.2, BLUE)
    _text(c, 322.4, Y_CAP - 2, f"原借款：{r.original_loan} 元", 6.6, BLUE)
    _text(c, 451.2, Y_CAP - 2, f"应退（补）款：{r.refund} 元", 6.6, BLUE)

    # ---- 签字栏 ----
    _line(c, LX, Y_SIGN, RX, Y_SIGN)
    _text(c, LX + 6, Y_SIGN + 1, "会计主管：" + (r.accounting_supervisor or ""), 7.7)
    _text(c, 124, Y_SIGN + 1, "复核：" + (r.reviewer or ""), 7.7)
    _text(c, 318, Y_SIGN + 1, "出纳：" + (r.cashier or ""), 7.7)
    _text(c, 448, Y_SIGN + 1, "报销人：" + (r.reimburser or r.applicant or ""), 7.7)

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
