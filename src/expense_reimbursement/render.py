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
    """模板样式大写：固定前缀佰仟万仟 + 逐位大写（0 位显示 零+单位，分位0补零分）。

    如 1704.12 -> 佰仟万仟壹仟柒佰零拾肆元壹角贰分；711.40 -> 佰仟万仟柒佰壹拾壹元肆角零分。
    """

    cn = "零壹贰叁肆伍陆柒捌玖"
    units = ["元", "拾", "佰", "仟", "万", "拾", "佰", "仟"]
    v = abs(Decimal(str(value)))
    integer = int(v)
    cents = int((v - integer) * 100 + Decimal("0.001"))
    jiao, fen = cents // 10, cents % 10
    digits = []
    n = integer
    for _ in range(8):
        digits.append(n % 10)
        n //= 10
    hi = 7
    while hi >= 0 and digits[hi] == 0:
        hi -= 1
    parts = []
    for pos in range(hi, -1, -1):
        d = digits[pos]
        if d == 0:
            if pos != 0:
                parts.append("零" + units[pos])
        else:
            parts.append(cn[d] + units[pos])
    if not parts:
        parts.append("零元")
    result = "".join(parts)
    if fen == 0 and jiao == 0:
        if not result.endswith("元"):
            result += "元"
        result += "整"
    else:
        if jiao:
            result += cn[jiao] + "角"
        elif fen:
            result += "零"
        if fen:
            result += cn[fen] + "分"
        else:
            result += "零分"
    return "佰仟万仟" + result


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

# 报销单整页缩放（只拉垂直方向填满 + 放大字号；水平坐标已近满宽不动）
FORM_SCALE = {"ys": 1.0, "y0": 0.0, "y_ref": 0.0, "fs": 1.0, "fx": 1.0}


def _ymap(y_top: float) -> float:
    return FORM_SCALE["y0"] + (y_top - FORM_SCALE["y_ref"]) * FORM_SCALE["ys"]


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
    sz = size * FORM_SCALE["fs"]
    c.setFont(FONT, sz)
    c.setFillColor(color)
    xx = x * FORM_SCALE["fx"]
    baseline = PAGE_H - (_ymap(y_top) + sz * TXT_MULT)
    if align == "center":
        c.drawCentredString(xx, baseline, s)
    elif align == "right":
        c.drawRightString(xx, baseline, s)
    else:
        c.drawString(xx, baseline, s)


def _line(
    c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float, w: float = 0.6
) -> None:
    c.setStrokeColor(BLUE)
    c.setLineWidth(w)
    c.line(x1 * FORM_SCALE["fx"], ty(_ymap(y1)), x2 * FORM_SCALE["fx"], ty(_ymap(y2)))



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
    sz = size * FORM_SCALE["fs"]
    width = sum(pdfmetrics.stringWidth(s, FONT, sz) for s, _ in parts)
    x = (center_x * FORM_SCALE["fx"]) - width / 2
    for s, col in parts:
        c.setFont(FONT, sz)
        c.setFillColor(col)
        c.drawString(x, PAGE_H - (_ymap(y_top) + sz * TXT_MULT), s)
        x += pdfmetrics.stringWidth(s, FONT, sz)


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
    global FORM_SCALE
    _prev_scale = FORM_SCALE
    FORM_SCALE = {'ys': 1.38, 'y0': 55.0, 'y_ref': 101.0, 'fs': 1.28, 'fx': 1.0}

    # ---- 标题（与下划线居中）----
    mid = PAGE_W / 2
    _text(c, mid, 101.3, "费   用   报   销   单", 15.4, BLUE, "center")
    for y in (116.9, 117.8, 118.3):
        _line(c, mid - 117.6, y, mid + 117.6, y, 0.5)

    # ---- 表头信息行（标签蓝，值黑；按放大后字宽排布，避免重叠）----
    _fs = FORM_SCALE["fs"]
    _label_x = 14.8
    _text(c, _label_x, 124.2, "报销部门：", 6.6, BLUE)
    _dept_x = _label_x + pdfmetrics.stringWidth("报销部门：", FONT, 6.6 * _fs) + 3
    _text(c, _dept_x, 124.2, r.department, 6.6, BLACK)
    _draw_date_centered(c, 297.5, 124.2, r.created_at, 6.6, BLACK, BLUE)
    pages_cn = "壹贰叁肆伍陆柒捌玖"[r.attachment_pages - 1]
    if not (1 <= r.attachment_pages <= 9):
        pages_cn = str(r.attachment_pages)
    _att_label = "单据及附件共 "
    _att_w = pdfmetrics.stringWidth(_att_label, FONT, 6.6 * _fs)
    _pages_w = pdfmetrics.stringWidth(pages_cn, FONT, 6.6 * _fs)
    _tail_w = pdfmetrics.stringWidth(" 页", FONT, 6.6 * _fs)
    _att_x = 583.0 - (_att_w + 3 + _pages_w + 3 + _tail_w)
    _text(c, _att_x, 124.2, _att_label, 6.6, BLUE)
    _text(c, _att_x + _att_w + 3, 124.2, pages_cn, 6.6, BLK)
    _text(c, _att_x + _att_w + 3 + _pages_w + 3, 124.2, " 页", 6.6, BLUE)

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
        _text(c, X_NOTE_R + 3, y, _fit(item.remarks or "", RX - X_NOTE_R - 6, 6.6), 6.6, BLK)

    # ---- 合计（值黑色）----
    _text(c, 156.2, 272.8, "合计", 6.6, BLUE)
    _print_amount_split(c, _split_amount_digits(r.total), 271.8)

    # ---- 金额大写区 ----
    _text(c, 40.0, 285.8, "金额", 7.7, BLUE, "center")
    _text(c, 40.0, 296.9, "（大写）", 7.7, BLUE, "center")
    cap = _capital_text(r.total)
    _draw_spaced_text(c, 70.5, 302.3, 291.9, cap, 8.2, BLACK)   # 逐字均匀铺满框，避让左线
    _text(c, 322.4, 291.9, "原借款：", 6.6, BLUE)
    if r.original_loan:
        _text(c, 349.0, 291.9, str(r.original_loan), 6.6, BLACK)
    _text(c, 421.0, 291.9, "元", 6.6, BLUE)
    _text(c, 451.2, 291.9, "应退（补）款：", 6.6, BLUE)
    if r.refund:
        _text(c, 500.0, 291.9, str(r.refund), 6.6, BLACK)
    _text(c, 560.0, 291.9, "元", 6.6, BLUE)

    # ---- 签字栏（只留标签，不填人员）----
    _text(c, 24.2, 310.4, "会计主管", 7.7, BLUE)
    _text(c, 124.2, 310.4, "复核", 7.7, BLUE)
    _text(c, 318.0, 310.4, "出纳", 7.7, BLUE)
    _text(c, 448.0, 310.4, "报销人", 7.7, BLUE)
    _text(c, 491.5, 310.4, r.reimburser or "陈兴华", 7.7, BLACK)

    c.showPage()
    c.save()
    FORM_SCALE = _prev_scale
    return output_path


# 凭证页图片内容区（标题与摘要之间，reportlab 左下原点 y）
REC_TOP = PAGE_H - 66      # 图片允许的最高底部坐标
REC_BOTTOM = 86            # 图片允许的最低底部坐标
REC_AVAIL = REC_TOP - REC_BOTTOM  # 可用垂直高度


def _draw_receipt_image(c: canvas.Canvas, image_path: Path) -> None:
    """把凭证图放进内容区：横图正向居中；竖长图旋转 90° 横放并居中。"""

    from PIL import Image

    with Image.open(image_path) as img:
        iw, ih = img.size
    maxw = PAGE_W - 40
    maxh = REC_AVAIL
    center_x = PAGE_W / 2
    center_y = REC_BOTTOM + REC_AVAIL / 2
    if ih > iw:
        # 竖长图：旋转 90° 横放，视觉宽=ih*s、视觉高=iw*s
        s = min(maxw / ih, maxh / iw)
        w = iw * s
        h = ih * s
        c.saveState()
        c.translate(center_x, center_y)
        c.rotate(90)
        c.drawImage(
            str(image_path),
            -w / 2,
            -h / 2,
            width=w,
            height=h,
            preserveAspectRatio=False,
        )
        c.restoreState()
    else:
        # 横图：正向水平+垂直居中
        ratio = min(maxw / iw, maxh / ih)
        dw = iw * ratio
        dh = ih * ratio
        cx = (PAGE_W - dw) / 2
        cy = REC_BOTTOM + (REC_AVAIL - dh) / 2
        c.drawImage(
            str(image_path),
            cx,
            cy,
            width=dw,
            height=dh,
            preserveAspectRatio=True,
        )


def render_receipt(
    image_path: Path | None, output_path: Path, summary: str = ""
) -> Path:
    """生成 A5 横向凭证 PDF。"""

    _register_font()
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))
    _text(c, PAGE_W / 2, PAGE_H - 40, "报销凭证", 14, BLUE, "center")
    if image_path and Path(image_path).exists():
        _draw_receipt_image(c, image_path)
        if summary:
            _text(c, PAGE_W / 2, 40, "识别摘要：" + summary, 8, BLUE, "center")
    else:
        _text(c, PAGE_W / 2, PAGE_H / 2, "（未提供凭证图片。）", 9, BLUE, "center")
    c.showPage()
    c.save()
    return output_path

def render_receipts(
    images: list[Path],
    output_path: Path,
    summaries: list[str] | None = None,
) -> Path:
    """生成 A5 凭证 PDF，每张凭证图一页。"""

    _register_font()
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))
    summaries = summaries or []
    for idx, image in enumerate(images):
        _text(c, PAGE_W / 2, PAGE_H - 40, f"报销凭证 {idx + 1}", 14, BLUE, "center")
        if Path(image).exists():
            _draw_receipt_image(c, image)
            if idx < len(summaries) and summaries[idx]:
                _text(c, PAGE_W / 2, 40, "识别摘要：" + summaries[idx], 8, BLUE, "center")
        else:
            _text(c, PAGE_W / 2, PAGE_H / 2, "（未提供凭证图片。）", 9, BLUE, "center")
        c.showPage()
    if not images:
        _text(c, PAGE_W / 2, PAGE_H / 2, "（无凭证图片。）", 9, BLUE, "center")
        c.showPage()
    c.save()
    return output_path
