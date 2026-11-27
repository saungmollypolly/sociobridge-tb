"""Draw Fig. 1 of the paper (the Observe-Decide-Act-Check architecture) at print size.

The figure is 238.5 pt wide in the paper's column; it is drawn at 300 dpi so that description text is
about 8 pt and titles about 9 pt when printed. Box heights follow from the wrapped text.
Needs Pillow and the Windows fonts Times New Roman and Leelawadee UI (for the Thai markers).

Usage:  python src/draw_fig1.py [results/fig1_architecture.png]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
S = 2                                   # supersampling factor (drawn at 2x, then reduced)
DPI = 300
W = round(238.5 / 72 * DPI)            # 994 px: the column width in the paper
PT = DPI / 72 * S                       # pixels per point at drawing scale

FONT_DIR = "C:/Windows/Fonts/"
BODY = ImageFont.truetype(FONT_DIR + "times.ttf", round(8.0 * PT))
TITLE = ImageFont.truetype(FONT_DIR + "timesbd.ttf", round(9.0 * PT))
THAI = ImageFont.truetype(FONT_DIR + "LeelawUI.ttf", round(7.4 * PT))
LABEL = ImageFont.truetype(FONT_DIR + "times.ttf", round(8.0 * PT))

INK, MUTED = (17, 17, 17), (70, 70, 70)
BLUE, BLUE_FILL = (42, 120, 214), (237, 244, 252)
GREY, GREY_FILL = (128, 128, 128), (243, 243, 241)
ORANGE, ORANGE_FILL = (232, 102, 60), (253, 243, 231)

LINE = 3 * S                            # box border width
PAD = round(5 * PT)                     # inner padding
GAP = round(8.5 * PT)                    # vertical gap between stage boxes (room for an arrow)


def wrap(text, font, width):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def line_h(font):
    a, d = font.getmetrics()
    return a + d


def block(title, body, width, extra_lines=()):
    """Return the lines (font, text) of one box and its height."""
    lines = [(TITLE, t) for t in wrap(title, TITLE, width - 2 * PAD)]
    for para in body:
        lines += [(BODY, t) for t in wrap(para, BODY, width - 2 * PAD)]
    lines += list(extra_lines)
    h = 2 * PAD + sum(line_h(f) for f, _ in lines) + round(1.5 * PT)
    return lines, h


def draw_lines(d, lines, x0, x1, y):
    y += PAD
    for i, (font, text) in enumerate(lines):
        color = INK if font is TITLE else MUTED
        tw = font.getlength(text)
        d.text(((x0 + x1 - tw) / 2, y), text, font=font, fill=color)
        y += line_h(font) + (round(1.5 * PT) if i == 0 and font is TITLE else 0)


def box(d, x0, y0, x1, y1, outline, fill, dashed=False):
    r = round(4 * PT)
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=None if dashed else outline,
                        width=LINE)
    if dashed:                          # dashed rounded border: draw dashes along each side
        dash, gap = round(5 * PT), round(3 * PT)
        for (ax, ay, bx, by) in [(x0 + r, y0, x1 - r, y0), (x0 + r, y1, x1 - r, y1),
                                 (x0, y0 + r, x0, y1 - r), (x1, y0 + r, x1, y1 - r)]:
            length = max(abs(bx - ax), abs(by - ay))
            pos = 0
            while pos < length:
                e = min(pos + dash, length)
                if ay == by:
                    d.line([(ax + pos, ay), (ax + e, ay)], fill=outline, width=LINE)
                else:
                    d.line([(ax, ay + pos), (ax, ay + e)], fill=outline, width=LINE)
                pos += dash + gap
        for cx, cy, start in [(x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270), (x1 - r, y1 - r, 0),
                              (x0 + r, y1 - r, 90)]:
            d.arc([cx - r, cy - r, cx + r, cy + r], start, start + 90, fill=outline, width=LINE)


def arrow_down(d, x, y0, y1, color=INK):
    head = round(3 * PT)
    d.line([(x, y0), (x, y1 - head)], fill=color, width=LINE)
    d.polygon([(x - head, y1 - head), (x + head, y1 - head), (x, y1)], fill=color)


def arrow_left(d, x0, x1, y, color):
    head = round(3 * PT)
    d.line([(x0, y), (x1 + head, y)], fill=color, width=LINE)
    d.polygon([(x1 + head, y - head), (x1 + head, y + head), (x1, y)], fill=color)


def main(out):
    w = W * S
    left_gutter = round(22 * PT)        # room for the repair loop on the left
    lib_w = round(66 * PT)
    col_gap = round(8 * PT)
    main_x0 = left_gutter
    main_x1 = w - lib_w - col_gap - LINE
    lib_x0, lib_x1 = main_x1 + col_gap, w - LINE
    full_x0, full_x1 = main_x0, lib_x1
    main_w = main_x1 - main_x0

    thai = (THAI, "(ครับ / ค่ะ, หนู, ผม, หัวหน้า, อาจารย์)")
    inp = block("Input", ["Thai source sentence + annotated social metadata (setting, roles, gender, "
                          "hierarchy, distance, intent)"], full_x1 - full_x0)
    stages = [
        ("1. OBSERVE (evaluated)", ["Build structured XML context block; identify Thai politeness markers"],
         [thai], False),
        ("2. DECIDE (implemented)", ["Propose 2–3 candidate politeness levels; commit to one with a stated "
                                    "reason (commitment step)"], [], True),
        ("3. ACT (evaluated)", ["LLM translates Thai → Burmese with the structured context (isolated, "
                               "stateless API call; XML output)"], [], False),
        ("4. CHECK (evaluated offline)", ["Rule-based checker R1–R9: format, script leakage, hedged forms, "
                                         "final particle, gender, address term, self-reference, casual "
                                         "pronoun, numbers"], [], False),
    ]
    stage_blocks = [block(t, b, main_w, extra) for t, b, extra, _ in stages]
    out_block = block("Output", ["Verified Burmese translation + rule trace"], full_x1 - full_x0)

    top = LINE
    y = top + inp[1] + GAP
    stage_y = []
    for lines, h in stage_blocks:
        stage_y.append((y, y + h))
        y += h + GAP
    out_y0 = y
    height = out_y0 + out_block[1] + LINE

    img = Image.new("RGB", (w, height), "white")
    d = ImageDraw.Draw(img)

    # input / output
    box(d, full_x0, top, full_x1, top + inp[1], GREY, GREY_FILL)
    draw_lines(d, inp[0], full_x0, full_x1, top)
    box(d, full_x0, out_y0, full_x1, out_y0 + out_block[1], GREY, GREY_FILL)
    draw_lines(d, out_block[0], full_x0, full_x1, out_y0)

    # stages and arrows
    cx = (main_x0 + main_x1) // 2
    arrow_down(d, cx, top + inp[1], stage_y[0][0])
    for i, ((lines, h), (y0, y1)) in enumerate(zip(stage_blocks, stage_y)):
        box(d, main_x0, y0, main_x1, y1, BLUE, BLUE_FILL, dashed=stages[i][3])
        draw_lines(d, lines, main_x0, main_x1, y0)
        nxt = stage_y[i + 1][0] if i + 1 < len(stage_y) else out_y0
        arrow_down(d, cx, y1, nxt)

    # mapping library
    ly0, ly1 = stage_y[0][0], stage_y[-1][1]
    box(d, lib_x0, ly0, lib_x1, ly1, ORANGE, ORANGE_FILL)
    lib_w_in = lib_x1 - lib_x0 - 2 * PAD
    lib_lines = [(TITLE, t) for t in ("Socio-", "Pragmatic", "Mapping", "Library")] + [(BODY, "")]
    for para in ("Compiled rules (knowledge compilation)", "",
                 "context → required and forbidden Burmese markers"):
        lib_lines += [(BODY, t) for t in (wrap(para, BODY, lib_w_in) if para else [""])]
    draw_lines(d, lib_lines, lib_x0, lib_x1, ly0 + round(2 * PT))
    for (y0, y1) in (stage_y[1], stage_y[3]):            # library feeds Decide and Check
        arrow_left(d, lib_x0, main_x1, (y0 + y1) // 2, ORANGE)

    # repair / select loop: from Check back to Act, on the left
    act_y, chk_y = stage_y[2], stage_y[3]
    ya, yb = (act_y[0] + act_y[1]) // 2, (chk_y[0] + chk_y[1]) // 2
    xl = round(9 * PT)
    head = round(3 * PT)
    d.line([(main_x0, yb), (xl, yb), (xl, ya), (main_x0 - head, ya)], fill=ORANGE, width=LINE, joint="curve")
    d.polygon([(main_x0 - head, ya - head), (main_x0 - head, ya + head), (main_x0, ya)], fill=ORANGE)
    label = "flagged → repair / select"
    tw, th = int(LABEL.getlength(label)) + 4, line_h(LABEL)
    tmp = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
    ImageDraw.Draw(tmp).text((2, 0), label, font=LABEL, fill=ORANGE)
    tmp = tmp.rotate(90, expand=True)
    lx = xl - tmp.width - round(1 * PT)
    img.paste(tmp, (max(0, lx), (ya + yb) // 2 - tmp.height // 2), tmp)

    img = img.resize((w // S, height // S), Image.LANCZOS)
    img.save(out, dpi=(DPI, DPI))
    print("wrote", out, img.size, f"-> {img.size[0] / DPI * 72:.1f} x {img.size[1] / DPI * 72:.1f} pt")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "results" / "fig1_architecture.png")
