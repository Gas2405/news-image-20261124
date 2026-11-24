#!/usr/bin/env python3
"""The World in One Day -- Tuesday 24 November 2026.

A self-contained news-poster generator for make.fun's news-image-20261124
bounty. It draws a 1024x1024 front page of the day's six biggest verified
stories with nothing but the Python standard library: its own tiny 5x7
pixel typeface, its own flat-shape drawing kit and its own PNG encoder,
so the output is byte-for-byte identical on every run, fully offline.

Run:  MAKEFUN_OUTPUT_DIR=out python3 main.py     (writes out/entry.png)
"""

import binascii
import math
import os
import struct
import zlib

W = H = 1024

# ---------------------------------------------------------------- palette
INK_TOP = (10, 17, 32)        # page background, top
INK_BOT = (22, 38, 63)        # page background, bottom
PANEL = (22, 37, 63)          # story card fill
PANEL_EDGE = (51, 80, 124)    # story card outline
CREAM = (245, 239, 224)       # headline ink
PAPER_DIM = (168, 186, 208)   # caption ink
GOLD = (233, 180, 76)         # masthead accent
SMOKE = (120, 134, 156)

# ------------------------------------------------------------- framebuffer
buf = bytearray(W * H * 3)


def px(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = c[0]
        buf[i + 1] = c[1]
        buf[i + 2] = c[2]


def rect(x, y, w, h, c):
    x0, x1 = max(0, x), min(W, x + w)
    y0, y1 = max(0, y), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    row = bytes(c) * (x1 - x0)
    for yy in range(y0, y1):
        i = (yy * W + x0) * 3
        buf[i:i + len(row)] = row


def rect_outline(x, y, w, h, t, c):
    rect(x, y, w, t, c)
    rect(x, y + h - t, w, t, c)
    rect(x, y, t, h, c)
    rect(x + w - t, y, t, h, c)


def disc(cx, cy, r, c):
    r2 = r * r
    for yy in range(cy - r, cy + r + 1):
        dx2 = r2 - (yy - cy) * (yy - cy)
        if dx2 < 0:
            continue
        dx = int(math.isqrt(dx2))
        rect(cx - dx, yy, 2 * dx + 1, 1, c)


def ring(cx, cy, r, t, c):
    # outline of a circle, drawn as short horizontal runs per row band
    for yy in range(cy - r, cy + r + 1):
        dy = yy - cy
        outer = r * r - dy * dy
        if outer < 0:
            continue
        dxo = int(math.isqrt(outer))
        inner_r = r - t
        inner = inner_r * inner_r - dy * dy
        if inner <= 0:
            rect(cx - dxo, yy, 2 * dxo + 1, 1, c)
        else:
            dxi = int(math.isqrt(inner))
            rect(cx - dxo, yy, dxo - dxi, 1, c)
            rect(cx + dxi + 1, yy, dxo - dxi, 1, c)


def line(x0, y0, x1, y1, c, th=2):
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    half = th // 2
    for i in range(steps + 1):
        x = x0 + (x1 - x0) * i // steps
        y = y0 + (y1 - y0) * i // steps
        rect(x - half, y - half, th, th, c)


def poly(points, c):
    # scanline fill of a simple polygon
    ys = [p[1] for p in points]
    for yy in range(min(ys), max(ys) + 1):
        xs = []
        n = len(points)
        for i in range(n):
            xa, ya = points[i]
            xb, yb = points[(i + 1) % n]
            if ya == yb:
                continue
            if (ya <= yy < yb) or (yb <= yy < ya):
                xs.append(xa + (yy - ya) * (xb - xa) // (yb - ya))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            rect(xs[i], yy, xs[i + 1] - xs[i] + 1, 1, c)


def blend(c1, c2, f):
    return tuple(round(a + (b - a) * f) for a, b in zip(c1, c2))


# ------------------------------------------------------------------- font
# A 5x7 pixel typeface, drawn for this poster. Each glyph is seven rows of
# five cells; '#' is ink, '.' is empty.
FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#..##", "#.#.#", "##..#", "#...#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."),
    "%": ("##..#", "##.#.", "....#", "...#.", "..#..", ".#...", "#.###"),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "/": ("....#", "....#", "...#.", "..#..", "..#..", ".#...", "#...."),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "\u00b7": (".....", ".....", ".....", ".##..", ".##..", ".....", "....."),
}


def text_w(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(x, y, s, scale, c, bold=False):
    for ch in s:
        glyph = FONT[ch]
        for row_i, row in enumerate(glyph):
            for col_i, cell in enumerate(row):
                if cell == "#":
                    gx = x + col_i * scale
                    gy = y + row_i * scale
                    rect(gx, gy, scale, scale, c)
                    if bold:
                        rect(gx + 1, gy, scale, scale, c)
        x += 6 * scale
    return x


def draw_text_c(cx, y, s, scale, c, bold=False):
    return draw_text(cx - text_w(s, scale) // 2, y, s, scale, c, bold)


# ------------------------------------------------------------------ icons
# Each icon is drawn inside a 40x40 box whose top-left corner is (x, y).

def icon_building(x, y, a, b):
    # apartment tower: small lit windows in a grid, a door, a jagged
    # crack down one corner and smoke curling off the roof
    rect(x + 9, y + 11, 16, 27, a)
    rect(x + 25, y + 19, 10, 19, a)
    for wy in (15, 20, 25, 30):
        for wx in (12, 17, 21):
            rect(x + wx, y + wy, 2, 3, b)
    for wy in (23, 28, 33):
        rect(x + 28, y + wy, 2, 3, b)
    rect(x + 14, y + 33, 4, 5, PANEL)
    line(x + 23, y + 11, x + 19, y + 19, PANEL, 2)
    line(x + 19, y + 19, x + 22, y + 26, PANEL, 2)
    line(x + 22, y + 26, x + 19, y + 33, PANEL, 2)
    disc(x + 13, y + 7, 4, SMOKE)
    disc(x + 19, y + 5, 3, SMOKE)
    disc(x + 24, y + 7, 2, SMOKE)


def icon_drone(x, y, a, b):
    # quadcopter from above -- four rotor rings on diagonal arms around
    # a camera body -- inside a targeting ring
    ring(x + 20, y + 20, 18, 1, b)
    line(x + 17, y + 17, x + 10, y + 10, a, 2)
    line(x + 23, y + 17, x + 30, y + 10, a, 2)
    line(x + 17, y + 23, x + 10, y + 30, a, 2)
    line(x + 23, y + 23, x + 30, y + 30, a, 2)
    for cx, cy in ((9, 9), (31, 9), (9, 31), (31, 31)):
        ring(x + cx, y + cy, 5, 2, a)
    rect(x + 16, y + 16, 8, 8, a)
    disc(x + 20, y + 20, 2, PANEL)


def icon_tanker(x, y, a, b):
    # tanker in a narrow strait, flame over the deck, waves below
    poly([(x + 3, y + 24), (x + 37, y + 24), (x + 32, y + 33), (x + 8, y + 33)], a)
    rect(x + 10, y + 19, 20, 5, a)
    rect(x + 27, y + 13, 5, 6, a)
    poly([(x + 15, y + 19), (x + 19, y + 9), (x + 23, y + 19)], (232, 110, 46))
    poly([(x + 17, y + 19), (x + 19, y + 13), (x + 21, y + 19)], GOLD)
    for wx in (4, 16, 28):
        line(x + wx, y + 37, x + wx + 4, y + 35, b, 2)
        line(x + wx + 4, y + 35, x + wx + 8, y + 37, b, 2)


def icon_satellite(x, y, a, b):
    # satellite on a tilted orbit, stars around
    for t_i in range(90):
        t = t_i / 90 * 2 * math.pi
        ex = 20 + 19 * math.cos(t)
        ey = 20 + 7.5 * math.sin(t)
        rx = 20 + (ex - 20) * math.cos(-0.5) - (ey - 20) * math.sin(-0.5)
        ry = 20 + (ex - 20) * math.sin(-0.5) + (ey - 20) * math.cos(-0.5)
        rect(x + int(rx) - 1, y + int(ry) - 1, 2, 2, b)
    rect(x + 17, y + 15, 7, 10, a)
    rect(x + 3, y + 17, 12, 6, b)
    rect(x + 26, y + 17, 12, 6, b)
    line(x + 6, y + 17, x + 6, y + 23, PANEL, 1)
    line(x + 10, y + 17, x + 10, y + 23, PANEL, 1)
    line(x + 29, y + 17, x + 29, y + 23, PANEL, 1)
    line(x + 33, y + 17, x + 33, y + 23, PANEL, 1)
    for sx, sy in ((6, 5), (33, 7), (10, 33), (30, 32)):
        line(x + sx - 2, y + sy, x + sx + 2, y + sy, CREAM, 1)
        line(x + sx, y + sy - 2, x + sx, y + sy + 2, CREAM, 1)


def icon_scales(x, y, a, b):
    # courthouse scales of justice
    rect(x + 19, y + 6, 3, 26, a)
    rect(x + 7, y + 9, 27, 3, a)
    disc(x + 20, y + 5, 3, b)
    for cx in (9, 31):
        line(x + cx, y + 12, x + cx - 4, y + 22, a, 1)
        line(x + cx, y + 12, x + cx + 4, y + 22, a, 1)
        poly([(x + cx - 6, y + 22), (x + cx + 6, y + 22), (x + cx, y + 27)], b)
    rect(x + 13, y + 32, 15, 3, a)


def icon_chip(x, y, a, b):
    # microchip with a rising arrow breaking out of its corner
    rect_outline(x + 11, y + 9, 19, 19, 2, a)
    rect(x + 16, y + 14, 9, 9, b)
    for i in range(3):
        rect(x + 7, y + 12 + i * 6, 4, 2, a)
        rect(x + 30, y + 12 + i * 6, 4, 2, a)
        rect(x + 14 + i * 6, y + 5, 2, 4, a)
        rect(x + 14 + i * 6, y + 28, 2, 4, a)
    line(x + 8, y + 36, x + 17, y + 28, (127, 176, 105), 3)
    line(x + 17, y + 28, x + 22, y + 32, (127, 176, 105), 3)
    line(x + 22, y + 32, x + 33, y + 19, (127, 176, 105), 3)
    poly([(x + 27, y + 18), (x + 34, y + 17), (x + 33, y + 24)], (127, 176, 105))


# ---------------------------------------------------------------- stories
# Headlines and captions: the day's news as reported on 24 November 2026,
# each story checked against at least two independent sources (research
# notes live beside this program's project folder, not in the image).
STORIES = [
    {
        "tag": "UKRAINE", "accent": (228, 87, 46), "icon": icon_building,
        "head": ("RUSSIA BOMBS", "ZAPORIZHZHIA"),
        "sub": ("HOMES HIT OVERNIGHT", "2 KILLED, 40 WOUNDED", "INCL. 4 CHILDREN"),
    },
    {
        "tag": "GAZA", "accent": (217, 142, 74), "icon": icon_drone,
        "head": ("ISRAEL KILLS", "HAMAS CHIEF"),
        "sub": ("SECURITY CHIEF ABU NAHEL", "AMONG 7+ DEAD IN GAZA", "IN TUESDAY STRIKES"),
    },
    {
        "tag": "IRAN", "accent": (46, 196, 182), "icon": icon_tanker,
        "head": ("IRAN: NO TALKS", "OVER HORMUZ"),
        "sub": ("SEVEN CONDITIONS FIRST", "TEHRAN: 3 TANKERS HIT", "MINES IN THE STRAIT"),
    },
    {
        "tag": "SPACE", "accent": (142, 124, 240), "icon": icon_satellite,
        "head": ("NUCLEAR SAT", "ALARM IN SPACE"),
        "sub": ("REPORTS: RUSSIAN WARHEAD", "SATELLITE IN WEEKS", "NATO VOWS DEFENCE"),
    },
    {
        "tag": "MYANMAR", "accent": (127, 176, 105), "icon": icon_scales,
        "head": ("14 NATIONS BACK", "GENOCIDE RULING"),
        "sub": ("ICJ FOUND GENOCIDE OF", "THE ROHINGYA IN 2017", "UK SANCTIONS 5 OFFICERS"),
    },
    {
        "tag": "TECH", "accent": (78, 165, 217), "icon": icon_chip,
        "head": ("HUANG BACK AT", "NVIDIA HELM"),
        "sub": ("TRUMP PUSHED THE BOARD", "STOCK LEAPS 33% AS AI", "TRADE ROARS BACK"),
    },
]


def draw_panel(px, py, story):
    accent = story["accent"]
    rect(px, py, 478, 230, PANEL)
    rect_outline(px, py, 478, 230, 2, PANEL_EDGE)
    rect(px, py, 6, 230, accent)
    # icon chip
    rect(px + 20, py + 14, 44, 44, blend(PANEL, accent, 0.25))
    story["icon"](px + 22, py + 16, accent, CREAM)
    draw_text(px + 78, py + 22, story["tag"], 4, accent, bold=True)
    # headline, two lines
    draw_text(px + 20, py + 68, story["head"][0], 5, CREAM, bold=True)
    draw_text(px + 20, py + 110, story["head"][1], 5, CREAM, bold=True)
    # captions, three short lines
    for i, s in enumerate(story["sub"]):
        draw_text(px + 20, py + 156 + i * 25, s, 3, PAPER_DIM)


def compose():
    # page background: a slow vertical deepening of the ink
    for yy in range(H):
        c = blend(INK_TOP, INK_BOT, yy / (H - 1))
        rect(0, yy, W, 1, c)
    # masthead
    draw_text_c(W // 2, 30, "THE WORLD IN ONE DAY", 5, GOLD)
    rect(214, 80, 596, 3, GOLD)
    draw_text_c(W // 2, 98, "TUESDAY", 6, CREAM)
    draw_text_c(W // 2, 150, "24 NOVEMBER 2026", 10, CREAM)
    rect(37, 236, 950, 3, GOLD)
    rect(37, 243, 950, 1, PANEL_EDGE)
    # six story cards, two columns by three rows
    for i, story in enumerate(STORIES):
        px = 28 + (i % 2) * (478 + 12)
        py = 258 + (i // 2) * (230 + 13)
        draw_panel(px, py, story)
    # colophon
    draw_text_c(W // 2, 986, "SIX STORIES \u00b7 ONE DAY \u00b7 24 NOVEMBER 2026", 3, PAPER_DIM)


def encode_png():
    raw = bytearray()
    row_bytes = W * 3
    for yy in range(H):
        raw.append(0)
        raw += buf[yy * row_bytes:(yy + 1) * row_bytes]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def main():
    compose()
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(encode_png())
    print("wrote", path)


if __name__ == "__main__":
    main()
