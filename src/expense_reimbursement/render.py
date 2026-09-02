"""生成 A5 横向财务报销单 PDF（精确复刻企业报销单模板）。"""

from __future__ import annotations

from datetime import date
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
BLUE = (49 / 255, 117 / 255, 201 / 255)
BLACK = (0.05, 0.05, 0.05)


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


CN_CAP_DIGITS = "零壹贰叁肆伍陆柒捌玖"
CN_CAP_UNITS = ["佰", "仟", "万", "仟", "佰", "拾", "元", "角", "分"]


def _capital_text(value: Decimal) -> str:
    """返回模板样式的中文大写金额（单位+数字分列，如 佰仟万仟贰佰零拾零元零角零分）。"""

    digits = _split_amount_digits(value)
    result = "佰仟万仟" + CN_CAP_DIGITS[int(digits[3])]
    for idx in (4, 5, 6, 7):
        result += CN_CAP_UNITS[idx] + CN_CAP_DIGITS[int(digits[idx])]
    result += "分"
    if int(digits[8]) != 0:
        result += CN_CAP_DIGITS[int(digits[8])]
    return result


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
TXT_MULT = 0.745


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
        _text(c, _amt_cx(i), y, digits[i], 6.6, BLACK, "center")



def _wrap_lines(text: str, max_w: float, size: float, max_lines: int = 3) -> list[str]:
    """按宽度把文本拆成多行（保留完整句子，不用省略号）。"""

    result: list[str] = []
    current = ""
    for ch in text:
        if pdfmetrics.stringWidth(current + ch, FONT, size) > max_w and current:
            result.append(current)
            if len(result) >= max_lines - 1:
                break
            current = ch
        else:
            current += ch
    if current and len(result) < max_lines:
        result.append(current)
    return result


CAP_DIGIT_CHARS = set("零壹贰叁肆伍陆柒捌玖")


def _draw_spaced_text(
    c: canvas.Canvas, x0: float, x1: float, y_top: float,
    text: str, size: float, digit_color: tuple[float, float, float],
) -> None:
    """逐字均匀排布文本框（两端对齐），数字用黑、单位用蓝。"""

    chars = list(text)
    n = len(chars)
    unit_color = BLUE
    if n <= 1:
        ch = text
        col = digit_color if ch in CAP_DIGIT_CHARS else unit_color
        _text(c, x0, y_top, ch, size, col)
        return
    step = (x1 - x0) / (n - 1)
    for i, ch in enumerate(chars):
        col = digit_color if ch in CAP_DIGIT_CHARS else unit_color
        _text(c, x0 + i * step, y_top, ch, size, col, "center")




def _draw_date_centered(
    c: canvas.Canvas, center_x: float, y_top: float,
    d: date, size: float,
    digit_color: tuple[float, float, float],
    unit_color: tuple[float, float, float],
) -> None:
    """绘制 YYYY年MM月DD日，数字黑、年月日蓝，整体居中于 center_x。"""

    _register_font()
    parts: list[tuple[str, tuple[float, float, float]]] = []
    y, mo, day = f"{d.year}", f"{d.month:02d}", f"{d.day:02d}"
    parts.append((y, digit_color))
    parts.append(("年", unit_color))
    parts.append((mo, digit_color))
    parts.append(("月", unit_color))
    parts.append((day, digit_color))
    parts.append(("日", unit_color))
    width = sum(pdfmetrics.stringWidth(s, FONT, size) for s, _ in parts)
    x = center_x - width / 2
    for s, col in parts:
        c.setFont(FONT, size)
        c.setFillColor(col)
        c.drawString(x, PAGE_H - (y_top + size * TXT_MULT), s)
        x += pdfmetrics.stringWidth(s, FONT, size)


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
    """生成 A5 横向财务报销单（精确复刻模板网格）。"""

    _register_font()
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))
    BLK = (0.05, 0.05, 0.05)

    # ---- 标题（与下划线居中）----
    mid = PAGE_W / 2
    _text(c, mid, 101.3, "费   用   报   销   单", 15.4, BLUE, "center")
    for y in (116.9, 117.8, 118.3):
        _line(c, mid - 117.6, y, mid + 117.6, y, 0.5)

    # ---- 表头信息行（标签蓝，值黑）----
    _text(c, 14.8, 124.2, "报销部门：", 6.6, BLUE)
    _text(c, 48.5, 124.2, r.department, 6.6, BLACK)
    _draw_date_centered(c, 297.5, 124.2, r.created_at, 6.6, BLACK, BLUE)
    pages_cn = "壹贰叁肆伍陆柒捌玖"[r.attachment_pages - 1]
    if not (1 <= r.attachment_pages <= 9):
        pages_cn = str(r.attachment_pages)
    _text(c, 453.7, 124.2, "单据及附件共 ", 6.6, BLUE)
    _text(c, 497.6, 124.2, pages_cn, 6.6, BLK)
    _text(c, 504.3, 124.2, " 页", 6.6, BLUE)

    # ---- 列表头（蓝色标签）----
    _text(c, 50.4, 141.2, "报销项目", 7.7, BLUE)
    _text(c, 207.7, 141.2, "摘要", 7.7, BLUE)
    _text(c, 365.7, 135.5, "金额", 7.7, BLUE)
    for i, unit in enumerate(AMT_UNITS):
        _text(c, _amt_cx(i), 148.2, unit, 5.6, BLUE, "center")
    _text(c, 439.4, 149.9, "备", 7.7, BLUE)
    _text(c, 439.4, 180.1, "注", 7.7, BLUE)
    for k, ch in enumerate("领导审批"):
        _text(c, 439.4, 225.1 + k * 10.0, ch, 7.7, BLUE)

    # ---- 网格（复刻模板双线）----
    LW = 0.5
    for x in (13.0, 13.5):
        _line(c, x, 134.0, x, 306.8, LW)
    for x in (118.3, 118.8):
        _line(c, x, 134.3, x, 268.6, LW)
    for x in (311.6, 312.0):
        _line(c, x, 134.3, x, 306.8, LW)
    for a, b in ((325.2, 325.7), (338.8, 339.3), (352.5, 353.0),
                 (366.1, 366.6), (379.8, 380.2), (393.4, 393.9),
                 (407.1, 407.5), (420.7, 421.2)):
        for x in (a, b):
            _line(c, x, 145.4, x, 284.5, LW)
    for x in (434.3, 434.8):
        _line(c, x, 134.3, x, 306.8, LW)
    for x in (451.9, 452.4):
        _line(c, x, 134.3, x, 284.5, LW)
    for x in (582.6, 583.1):
        _line(c, x, 134.3, x, 306.8, LW)

    _line(c, 13.0, 133.8, 583.1, 133.8, LW)
    _line(c, 13.5, 134.3, 583.1, 134.3, LW)
    _line(c, 312.0, 144.9, 434.8, 144.9, LW)
    _line(c, 312.0, 145.4, 434.8, 145.4, LW)
    rows_a = [156.1, 172.1, 188.1, 220.1, 236.1, 252.1, 268.1]
    for y in rows_a:
        _line(c, 13.5, y, 434.8, y, LW)
        _line(c, 13.5, y + 0.4, 434.8, y + 0.4, LW)
    for y in (204.1, 204.5):
        _line(c, 13.0, y, 583.1, y, LW)
    _line(c, 13.5, 284.1, 583.1, 284.1, LW)
    _line(c, 13.5, 284.5, 583.1, 284.5, LW)
    _line(c, 13.5, 306.3, 583.1, 306.3, LW)
    _line(c, 13.0, 306.8, 583.1, 306.8, LW)
    for x in (65.8, 66.2):
        _line(c, x, 284.5, x, 306.8, LW)

    # ---- 备注（显示在"备注"标签右侧空白区，多行，黑色）----
    if r.remarks:
        rem_w = RX - 456.0 - 4
        rem_lines = _wrap_lines(r.remarks, rem_w, 6.6, max_lines=3)
        for li, line in enumerate(rem_lines):
            _text(c, 456.0, 148.0 + li * 9.0, line, 6.6, BLACK)

    # ---- 数据行（值黑色）----
    for row_idx, item in enumerate(r.items):
        y = 160.8 + row_idx * ROW_H
        _text(c, 49.6, y, _fit(item.project or "", 56, 6.6), 6.6, BLK)
        _text(c, 144.5, y, _fit(item.description or "", X_SUMM_R - 144.5 - 4, 6.6), 6.6, BLK)
        _print_amount_split(c, _split_amount_digits(item.amount), y - 1)
        _text(c, 434.8 + 3, y, _fit(item.remarks or "", RX - 434.8 - 6, 6.6), 6.6, BLK)

    # ---- 合计（值黑色）----
    _text(c, 156.2, 272.8, "合计", 6.6, BLUE)
    _print_amount_split(c, _split_amount_digits(r.total), 271.8)

    # ---- 金额大写区 ----
    _text(c, 40.0, 285.8, "金额", 7.7, BLUE, "center")
    _text(c, 40.0, 296.9, "（大写）", 7.7, BLUE, "center")
    cap = _capital_text(r.total)
    _draw_spaced_text(c, 70.5, 302.3, 291.9, cap, 8.2, BLACK)   # 逐字均匀铺满框，避让左线
    _text(c, 322.4, 291.9, "原借款：", 6.6, BLUE)
    loan = str(r.original_loan) if r.original_loan else ""
    _text(c, 349.0, 291.9, loan, 6.6, BLACK)
    _text(c, 451.2, 291.9, "应退（补）款：", 6.6, BLUE)
    refund = str(r.refund) if r.refund else ""
    _text(c, 500.0, 291.9, refund, 6.6, BLACK)

    # ---- 签字栏（只留标签，不填人员）----
    _text(c, 24.2, 310.4, "会计主管", 7.7, BLUE)
    _text(c, 124.2, 310.4, "复核", 7.7, BLUE)
    _text(c, 318.0, 310.4, "出纳", 7.7, BLUE)
    _text(c, 448.0, 310.4, "报销人", 7.7, BLUE)
    _text(c, 491.5, 310.4, r.reimburser or "陈兴华", 7.7, BLACK)

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
