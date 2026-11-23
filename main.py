#!/usr/bin/env python3
"""Sum up 23 November's world news in one image.

Draws a one-page broadsheet front page for Monday 23 November 2026:
36 dated stories across 7 regions, three illustrated lead stories,
twelve illustrated cards, a schematic world map with pins, an
in-brief list and a date check. Python 3.13 standard library only;
the PNG encoder and the 5x7 bitmap font are written here from scratch.
Deterministic: two runs write identical bytes.

Run: mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
Writes out/entry.png (1024x1024, under 1 MiB).
"""

import os
import struct
import zlib
from pathlib import Path

W, H = 1024, 1024

# ---- palette ---------------------------------------------------------
PAPER = (247, 242, 231)
PAPER_DK = (238, 231, 214)
INK = (24, 24, 24)
NAVY = (24, 38, 68)
NAVY_LT = (43, 62, 102)
RED = (176, 30, 36)
RED_DK = (140, 20, 26)
TEAL = (15, 106, 104)
BLUE = (36, 84, 158)
ORANGE = (196, 106, 22)
GREEN = (46, 110, 54)
PURPLE = (104, 64, 130)
GREY = (90, 90, 86)
WHITE = (255, 255, 255)
GOLD = (198, 158, 52)
SKY = (168, 196, 214)
SEA = (52, 96, 128)
SAND = (214, 186, 138)
NIGHT = (16, 24, 48)


# ---- canvas ----------------------------------------------------------
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(bg * (w * h))

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = c

    def rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = c

    def frame(self, x, y, w, h, c, t=1):
        self.rect(x, y, w, t, c)
        self.rect(x, y + h - t, w, t, c)
        self.rect(x, y, t, h, c)
        self.rect(x + w - t, y, t, h, c)

    def hline(self, x, y, w, c, t=1):
        self.rect(x, y, w, t, c)

    def vline(self, x, y, h, c, t=1):
        self.rect(x, y, t, h, c)

    def line(self, x0, y0, x1, y1, c):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set(x0, y0, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disc(self, cx, cy, r, c):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.set(xx, yy, c)

    def ring(self, cx, cy, r, c, t=2):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                d = (xx - cx) ** 2 + (yy - cy) ** 2
                if (r - t) ** 2 <= d <= r * r:
                    self.set(xx, yy, c)

    def tri(self, ax, ay, bx, by, cx, cy, c):
        # scanline fill of a triangle
        pts = sorted([(ax, ay), (bx, by), (cx, cy)], key=lambda p: p[1])
        (x0, y0), (x1, y1), (x2, y2) = pts
        for y in range(y0, y2 + 1):
            xs = []
            for (px, py), (qx, qy) in (((x0, y0), (x1, y1)),
                                       ((x1, y1), (x2, y2)),
                                       ((x0, y0), (x2, y2))):
                if py == qy:
                    continue
                if min(py, qy) <= y <= max(py, qy):
                    t = (y - py) / (qy - py)
                    xs.append(px + t * (qx - px))
            if len(xs) >= 2:
                for x in range(int(min(xs)), int(max(xs)) + 1):
                    self.set(x, y, c)


# ---- 5x7 bitmap font --------------------------------------------------
# Each glyph is 7 rows of 5 bits, '1' = ink.
FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'D': ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'J': ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    'K': ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'Q': ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'V': ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    'W': ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    'X': ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    'Y': ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    'Z': ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    'a': ("00000", "00000", "01110", "00001", "01111", "10001", "01111"),
    'b': ("10000", "10000", "11110", "10001", "10001", "10001", "11110"),
    'c': ("00000", "00000", "01110", "10001", "10000", "10001", "01110"),
    'd': ("00001", "00001", "01111", "10001", "10001", "10001", "01111"),
    'e': ("00000", "00000", "01110", "10001", "11111", "10000", "01110"),
    'f': ("00110", "01000", "01000", "11110", "01000", "01000", "01000"),
    'g': ("00000", "01111", "10001", "10001", "01111", "00001", "01110"),
    'h': ("10000", "10000", "11110", "10001", "10001", "10001", "10001"),
    'i': ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
    'j': ("00010", "00000", "00110", "00010", "00010", "00010", "01100"),
    'k': ("10000", "10000", "10010", "10100", "11000", "10100", "10010"),
    'l': ("01100", "00100", "00100", "00100", "00100", "00100", "01110"),
    'm': ("00000", "00000", "11010", "10101", "10101", "10101", "10101"),
    'n': ("00000", "00000", "11110", "10001", "10001", "10001", "10001"),
    'o': ("00000", "00000", "01110", "10001", "10001", "10001", "01110"),
    'p': ("00000", "00000", "11110", "10001", "10001", "11110", "10000"),
    'q': ("00000", "00000", "01111", "10001", "10001", "01111", "00001"),
    'r': ("00000", "00000", "10110", "11001", "10000", "10000", "10000"),
    's': ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
    't': ("01000", "01000", "11100", "01000", "01000", "01000", "00110"),
    'u': ("00000", "00000", "10001", "10001", "10001", "10011", "01101"),
    'v': ("00000", "00000", "10001", "10001", "10001", "01010", "00100"),
    'w': ("00000", "00000", "10001", "10101", "10101", "10101", "01010"),
    'x': ("00000", "00000", "10001", "01010", "00100", "01010", "10001"),
    'y': ("00000", "00000", "10001", "10001", "01111", "00001", "01110"),
    'z': ("00000", "00000", "11111", "00010", "00100", "01000", "11111"),
}

FONT.update({
    '0': ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    '1': ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    '2': ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    '3': ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    '4': ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    '5': ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    '6': ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    '7': ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    '8': ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    '9': ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ',': ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    ':': ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ';': ("00000", "01100", "01100", "00000", "01100", "00100", "01000"),
    '!': ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    '?': ("01110", "10001", "00001", "00110", "00100", "00000", "00100"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    '"': ("01010", "01010", "00000", "00000", "00000", "00000", "00000"),
    '(': ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ')': ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    '/': ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    '%': ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    '$': ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    '&': ("01100", "10010", "10100", "01000", "10101", "10010", "01101"),
    '+': ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    '=': ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    '*': ("00000", "10101", "01110", "11111", "01110", "10101", "00000"),
    '_': ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    '[': ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    ']': ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
    '<': ("00010", "00100", "01000", "10000", "01000", "00100", "00010"),
    '>': ("01000", "00100", "00010", "00001", "00010", "00100", "01000"),
    '#': ("01010", "01010", "11111", "01010", "11111", "01010", "01010"),
})


def text_w(s, scale):
    """Pixel width of a string at the given scale."""
    return len(s) * 6 * scale


def draw_text(cv, x, y, s, color, scale=1, bold=False):
    """Draw left-aligned text; returns the x just past the text."""
    for ch in s:
        glyph = FONT.get(ch, FONT['?'])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == '1':
                    cv.rect(x + col * scale, y + row * scale,
                            scale, scale, color)
                    if bold:
                        cv.rect(x + col * scale + 1, y + row * scale,
                                scale, scale, color)
        x += 6 * scale
    return x


def draw_text_center(cv, cx, y, s, color, scale=1, bold=False):
    draw_text(cv, cx - text_w(s, scale) // 2, y, s, color, scale, bold)


def draw_text_right(cv, rx, y, s, color, scale=1, bold=False):
    draw_text(cv, rx - text_w(s, scale), y, s, color, scale, bold)


def wrap(s, scale, max_w):
    """Greedy word wrap; returns a list of lines fitting max_w pixels."""
    words = s.split(' ')
    lines, cur = [], ''
    for word in words:
        trial = word if not cur else cur + ' ' + word
        if text_w(trial, scale) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_para(cv, x, y, s, color, scale, max_w, leading=None):
    """Draw a wrapped paragraph; returns y just past the last line."""
    lh = leading if leading is not None else 7 * scale + 2
    for line in wrap(s, scale, max_w):
        draw_text(cv, x, y, line, color, scale)
        y += lh
    return y


# ---- PNG encoder (stdlib only, deterministic) --------------------------
def png_bytes(cv):
    def chunk(kind, data):
        out = struct.pack('>I', len(data)) + kind + data
        out += struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)
        return out

    raw = bytearray()
    for yy in range(cv.h):
        raw.append(0)  # filter: none
        base = yy * cv.w * 3
        raw += cv.px[base:base + cv.w * 3]
    ihdr = struct.pack('>IIBBBBB', cv.w, cv.h, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(bytes(raw), 9))
            + chunk(b'IEND', b''))


# ---- illustrations -----------------------------------------------------
def scene_cop31(cv, x, y, w, h):
    """Antalya summit hall: empty chairs, a long table, no deal."""
    cv.rect(x, y, w, h, (222, 226, 214))
    cv.rect(x, y, w, 26, NAVY_LT)
    draw_text(cv, x + 8, y + 8, "ANTALYA - THE FINAL PLENARY", WHITE, 1)
    # globe on the wall
    cv.disc(x + 46, y + 58, 22, TEAL)
    cv.disc(x + 40, y + 52, 7, GREEN)
    cv.disc(x + 54, y + 64, 9, GREEN)
    cv.ring(x + 46, y + 58, 22, INK, 1)
    # long table
    cv.rect(x + 90, y + 78, w - 110, 10, (122, 84, 44))
    cv.rect(x + 96, y + 88, 6, 22, (90, 60, 30))
    cv.rect(x + w - 30, y + 88, 6, 22, (90, 60, 30))
    # delegates: heads and shoulders behind the table
    for i in range(6):
        dx = x + 150 + i * 30
        cv.disc(dx, y + 66, 9, (216, 178, 140))
        cv.rect(dx - 11, y + 74, 22, 8, NAVY if i % 2 == 0 else RED_DK)
    # gavel, laid down
    cv.rect(x + w - 78, y + 52, 34, 8, (122, 84, 44))
    cv.rect(x + w - 64, y + 60, 6, 16, (122, 84, 44))
    # red NO DEAL stamp
    cv.frame(x + 14, y + h - 34, 118, 26, RED, 2)
    draw_text(cv, x + 20, y + h - 28, "NO DEAL", RED, 2, bold=True)


def scene_riyadh(cv, x, y, w, h):
    """Night over Riyadh: interceptors climb, a radar turns."""
    cv.rect(x, y, w, h, NIGHT)
    for sx, sy in ((12, 10), (40, 26), (88, 8), (150, 18), (210, 10),
                   (260, 30), (300, 12), (60, 44), (180, 40)):
        cv.disc(x + sx, y + sy, 1, WHITE)
    cv.disc(x + 272, y + 26, 12, (226, 220, 196))  # moon
    # skyline
    for bx, bw, bh in ((0, 34, 34), (40, 26, 48), (72, 30, 30),
                       (250, 30, 44), (286, 34, 30)):
        cv.rect(x + bx, y + h - bh, bw, bh, (30, 42, 72))
        for wy in range(y + h - bh + 6, y + h - 6, 10):
            cv.rect(x + bx + 6, wy, 4, 5, GOLD)
    # radar dish
    cv.line(x + 150, y + h - 20, x + 150, y + h - 52, WHITE)
    cv.tri(x + 138, y + h - 50, x + 162, y + h - 50, x + 150, y + h - 66,
           WHITE)
    # two interceptor trails
    cv.line(x + 120, y + h - 30, x + 190, y + 18, GOLD)
    cv.line(x + 200, y + h - 30, x + 250, y + 30, GOLD)
    cv.disc(x + 190, y + 18, 3, GOLD)
    cv.disc(x + 250, y + 30, 3, GOLD)
    cv.rect(x, y + h - 24, w, 24, (10, 14, 30))
    draw_text(cv, x + 8, y + h - 17, "3RD NIGHT RUNNING - BOTH INTERCEPTED",
              WHITE, 1)


def scene_mercury(cv, x, y, w, h):
    """BepiColombo arrives: cratered Mercury, small probe, black sky."""
    cv.rect(x, y, w, h, (8, 10, 22))
    for sx, sy in ((14, 12), (52, 30), (96, 8), (140, 22), (210, 12),
                   (262, 34), (300, 10), (30, 52), (120, 46), (240, 50)):
        cv.disc(x + sx, y + sy, 1, WHITE)
    # Mercury
    cv.disc(x + 96, y + 66, 42, (196, 150, 104))
    for cx, cy, r in ((80, 52, 8), (108, 74, 10), (88, 84, 6),
                      (116, 50, 5), (70, 70, 5)):
        cv.disc(x + cx, y + cy, r, (164, 120, 80))
        cv.ring(x + cx, y + cy, r, (140, 100, 66), 1)
    cv.ring(x + 96, y + 66, 42, INK, 1)
    # spacecraft: body, panels, dish
    cv.rect(x + 196, y + 40, 26, 16, (210, 210, 205))
    cv.rect(x + 176, y + 44, 20, 8, (36, 84, 158))
    cv.rect(x + 222, y + 44, 20, 8, (36, 84, 158))
    cv.line(x + 209, y + 56, x + 209, y + 66, WHITE)
    cv.disc(x + 209, y + 68, 4, WHITE)
    cv.line(x + 222, y + 48, x + 246, y + 30, GOLD)
    cv.disc(x + 246, y + 30, 3, GOLD)
    draw_text(cv, x + 8, y + h - 18, "8 YEARS - 10 BILLION KM - ORBIT AT LAST",
              WHITE, 1)


def thumb_icon(cv, x, y, w, h, kind):
    """Small flat icon strip for a medium card."""
    bg = {
        'flags': (232, 222, 196), 'cricket': (46, 110, 54),
        'ballot': (36, 84, 158), 'capitol': (232, 226, 210),
        'badge': (24, 38, 68), 'ship': (52, 96, 128),
        'drone': (16, 24, 48), 'fire': (140, 20, 26),
        'city': (90, 90, 86), 'tanker': (30, 42, 72),
        'un': (36, 84, 158), 'school': (196, 106, 22),
    }.get(kind, PAPER_DK)
    cv.rect(x, y, w, h, bg)
    if kind == 'flags':
        cv.rect(x + 12, y + 6, 34, 18, (255, 153, 51))
        cv.rect(x + 12, y + 12, 34, 6, WHITE)
        cv.rect(x + 12, y + 18, 34, 6, (19, 136, 8))
        cv.rect(x + 56, y + 6, 34, 18, (220, 20, 60))
        cv.disc(x + 73, y + 15, 5, (0, 56, 147))
    elif kind == 'cricket':
        cv.line(x + 20, y + 6, x + 44, y + 24, (222, 200, 150))
        cv.line(x + 22, y + 4, x + 46, y + 22, (222, 200, 150))
        cv.disc(x + 62, y + 10, 4, RED)
        draw_text(cv, x + 76, y + 9, "720/9", WHITE, 2, bold=True)
    elif kind == 'ballot':
        cv.rect(x + 14, y + 8, 30, 18, WHITE)
        cv.rect(x + 20, y + 5, 18, 4, INK)
        cv.line(x + 52, y + 22, x + 60, y + 12, WHITE)
        cv.line(x + 60, y + 12, x + 76, y + 26, WHITE)
        draw_text(cv, x + 84, y + 9, "723 SEATS", WHITE, 1)
    elif kind == 'capitol':
        cv.disc(x + 30, y + 20, 12, WHITE)
        cv.rect(x + 18, y + 20, 24, 6, WHITE)
        for cx in (20, 30, 40):
            cv.rect(x + cx, y + 12, 3, 8, WHITE)
        draw_text(cv, x + 52, y + 9, "DEC 1 VOTE", INK, 1)
    elif kind == 'badge':
        cv.disc(x + 24, y + 14, 9, GOLD)
        draw_text(cv, x + 40, y + 8, "FBI 10 MOST WANTED", WHITE, 1)
        draw_text(cv, x + 40, y + 18, "11 DEAD IN SINALOA", GOLD, 1)
    elif kind == 'ship':
        cv.rect(x + 12, y + 16, 52, 10, (30, 30, 30))
        cv.rect(x + 26, y + 6, 8, 10, (30, 30, 30))
        cv.tri(x + 66, y + 16, x + 72, y + 6, x + 78, y + 16, ORANGE)
        cv.tri(x + 78, y + 16, x + 84, y + 8, x + 90, y + 16, GOLD)
        cv.rect(x, y + 26, w, 4, (120, 170, 200))
    elif kind == 'drone':
        cv.line(x + 14, y + 14, x + 34, y + 14, WHITE)
        cv.line(x + 24, y + 6, x + 24, y + 22, WHITE)
        cv.disc(x + 24, y + 14, 3, RED)
        draw_text(cv, x + 44, y + 9, "14 MISSING", WHITE, 1)
    elif kind == 'fire':
        cv.rect(x + 12, y + 12, 34, 14, (60, 60, 60))
        cv.tri(x + 18, y + 12, x + 24, y + 2, x + 30, y + 12, ORANGE)
        cv.tri(x + 30, y + 12, x + 36, y + 4, x + 42, y + 12, GOLD)
        draw_text(cv, x + 54, y + 9, "50 STILL MISSING", WHITE, 1)
    elif kind == 'city':
        for bx, bw, bh in ((10, 16, 18), (30, 12, 24), (46, 18, 14)):
            cv.rect(x + bx, y + 26 - bh, bw, bh, INK)
        cv.line(x + 70, y + 26, x + 78, y + 8, (200, 200, 200))
        cv.line(x + 84, y + 26, x + 92, y + 10, (200, 200, 200))
        draw_text(cv, x + 100, y + 9, "9 KILLED IN 48 HOURS", WHITE, 1)
    elif kind == 'tanker':
        cv.rect(x + 12, y + 16, 56, 9, (20, 20, 20))
        cv.rect(x + 56, y + 8, 10, 8, (20, 20, 20))
        cv.tri(x + 72, y + 16, x + 78, y + 6, x + 84, y + 16, ORANGE)
        draw_text(cv, x + 92, y + 9, "25 HIT IN A WEEK", WHITE, 1)
    elif kind == 'un':
        cv.disc(x + 24, y + 14, 10, WHITE)
        cv.ring(x + 24, y + 14, 10, BLUE, 1)
        cv.line(x + 14, y + 14, x + 34, y + 14, BLUE)
        cv.line(x + 24, y + 4, x + 24, y + 24, BLUE)
        draw_text(cv, x + 42, y + 9, "TALKS GO ON", WHITE, 1)
    elif kind == 'school':
        cv.rect(x + 12, y + 8, 30, 18, WHITE)
        cv.rect(x + 18, y + 12, 18, 2, INK)
        cv.rect(x + 18, y + 17, 18, 2, INK)
        draw_text(cv, x + 50, y + 9, "AI CHEATING SCANDAL", WHITE, 1)


# ---- schematic world map ----------------------------------------------
# 62 x 22 grid, '#' = land. Schematic, not to scale.
MAP_ROWS = [
    "..............................................................",
    "..............................................................",
    "......######.....###..........................................",
    "....##########...##.......###....####################.........",
    ".....##########.........###############################.......",
    "......########..........##############################.......",
    ".......######...........####..#######################........",
    "........####....##.......###...##################..##.........",
    ".........##....####.......##....###############....###.........",
    ".........##...######............#############......##..........",
    "..........#....#####............###########...................",
    "..........#.....###..............#########....................",
    "..........##....###.....##.........#######.....................",
    "...........##....##....####.........######..........##.........",
    "............##...##...######.........####..........###.........",
    ".............#...#....#######.........###..........####........",
    ".............#........########.........##..........#####.......",
    "......................#########.........##.........####........",
    ".......................#######....................###.........",
    "........................#####......................##.........",
    ".........................###..................................",
    "..........................#...................................",
]
# (grid x, grid y) per story number on the map
PINS = {
    1: (35, 7), 2: (39, 10), 4: (44, 9), 5: (57, 21), 6: (48, 10),
    7: (9, 7), 8: (6, 10), 9: (33, 4), 10: (31, 5), 11: (47, 13),
    12: (36, 9), 13: (40, 10), 14: (11, 6), 15: (50, 7),
}


# ---- the day's news (verified against wires, 23 Nov 2026 morning) -----
STATS = [
    ("44", "hours of overtime before COP31 fell"),
    ("0", "fossil-fuel mentions in the final draft"),
    ("25", "tankers hit in a week off Hormuz"),
    ("720/9", "India's record Test total in NZ"),
    ("11", "dead in the Sinaloa cartel raid"),
    ("1,661", "Gaza toll since the Oct 2025 ceasefire"),
]

REGIONS = [
    ("EUROPE 9", 9, TEAL), ("MID EAST 6", 6, RED),
    ("AMERICAS 3", 3, BLUE), ("ASIA-PAC 9", 9, ORANGE),
    ("AFRICA 2", 2, GREEN), ("OCEANIA 1", 1, PURPLE),
    ("WORLD 6", 6, GREY),
]

LEADS = [
    {
        "num": 1, "scene": scene_cop31, "color": RED,
        "kicker": "1 ANTALYA, TURKIYE - CLIMATE - 23 NOV",
        "headline": "COP31 ends with no deal",
        "body": "44 hours of overtime, no deal. The EU and island "
                "states reject a draft that never names fossil fuels.",
        "source": "Reuters, BBC, AP",
    },
    {
        "num": 2, "scene": scene_riyadh, "color": RED_DK,
        "kicker": "2 RIYADH, SAUDI ARABIA - MIDDLE EAST - 23 NOV",
        "headline": "Riyadh hit a third night",
        "body": "A Houthi drone and missile fired Sunday, both "
                "intercepted. Bahrain demands UN action.",
        "source": "AP, Arab News",
    },
    {
        "num": 3, "scene": scene_mercury, "color": NAVY,
        "kicker": "3 SPACE - SCIENCE - 21 NOV",
        "headline": "BepiColombo reaches Mercury",
        "body": "In orbit after eight years. ESA says a thruster "
                "glitch cut the burn short; the craft is safe.",
        "source": "Reuters, ESA",
    },
]

MEDIUM = [
    {"num": 4, "icon": "flags",
     "kicker": "4 NEW DELHI - ASIA-PACIFIC - 23 NOV",
     "headline": "Nepal PM meets Modi in Delhi",
     "body": "Balendra Shah meets PM Modi in Delhi on Monday, day "
             "two of his state visit."},
    {"num": 5, "icon": "cricket",
     "kicker": "5 WELLINGTON - CRICKET - 22 NOV",
     "headline": "India 720 for 9: a record in NZ",
     "body": "India pile up a record 720/9 declared, the biggest "
             "Test total in New Zealand."},
    {"num": 6, "icon": "ballot",
     "kicker": "6 HONG KONG - ELECTION - 22 NOV",
     "headline": "Hong Kong votes: 723 seats",
     "body": "856 candidates contest 723 seats that pick Hong "
             "Kong's next chief executive."},
    {"num": 7, "icon": "capitol",
     "kicker": "7 WASHINGTON - AMERICAS - 23 NOV",
     "headline": "Schumer faces a Dec 1 challenge",
     "body": "Schumer faces a Dec 1 secret-ballot challenge from "
             "Chris Van Hollen."},
    {"num": 8, "icon": "badge",
     "kicker": "8 SINALOA, MEXICO - AMERICAS - 20 NOV",
     "headline": "El Chapo Isidro caught in Sinaloa",
     "body": "FBI most-wanted boss Meza Flores seized in Guasave; "
             "11 dead, 8 held."},
    {"num": 9, "icon": "ship",
     "kicker": "9 GULF OF FINLAND - EUROPE - 22 NOV",
     "headline": "Sparta II still burning off Finland",
     "body": "Sparta II ablaze after a drone strike; crew of 16 "
             "evacuated."},
    {"num": 10, "icon": "drone",
     "kicker": "10 KYIV REGION - EUROPE - 22 NOV",
     "headline": "Kyiv: 14 missing after drone hit",
     "body": "At least 14 missing after a Russian drone hit a "
             "building in Dymer."},
    {"num": 11, "icon": "fire",
     "kicker": "11 CIKANDE - ASIA-PACIFIC - 22 NOV",
     "headline": "Candy-factory fire in Cikande",
     "body": "Seven body bags found, about 50 missing after a "
             "candy-factory fire."},
    {"num": 12, "icon": "city",
     "kicker": "12 GAZA CITY - MIDDLE EAST - 23 NOV",
     "headline": "Gaza: nine killed in 48 hours",
     "body": "Israeli strikes kill nine in 48 hours; toll since "
             "Oct 2025: 1,661."},
    {"num": 13, "icon": "tanker",
     "kicker": "13 STRAIT OF HORMUZ - ENERGY - 23 NOV",
     "headline": "25 tankers hit around Hormuz",
     "body": "At least 25 tankers hit around the strait in a "
             "week; oil flow drops."},
    {"num": 14, "icon": "un",
     "kicker": "14 UNITED NATIONS - WORLD - 23 NOV",
     "headline": "Lethal-AI talks go on at the UN",
     "body": "Nations agree to keep negotiating on lethal "
             "autonomous weapons at the UN."},
    {"num": 15, "icon": "school",
     "kicker": "15 SEOUL - ASIA-PACIFIC - 23 NOV",
     "headline": "Seoul minister quits in AI scandal",
     "body": "South Korea's education minister resigns over an AI "
             "exam-cheating scandal."},
]

BRIEF = [
    (16, "Nigeria: boat capsizes, 24 dead"),
    (17, "Brazil storm kills 4, injures 162"),
    (18, "DR Congo: Ebola toll 5,678 by mid-Nov"),
    (19, "Kryvyi Rih strike: 2 dead, 60 hurt"),
    (20, "Brussels Airport hit by strike chaos"),
    (21, "De Gennaro, 78, found dead in Tuscany"),
    (22, "Likud and Yashar resume unity talks"),
    (23, "BBC Verify: Crimea Bridge blast film"),
    (24, "Trump seeks permanent Iran deal"),
    (25, "Bitcoin rebounds from a two-year low"),
    (26, "France: cost protests, 6th Saturday"),
    (27, "Ganga treaty faces Dec 12 expiry"),
    (28, "Lisbon marches over living costs"),
    (29, "Myanmar calls ASEAN ruling unfair"),
    (30, "MP Wadkute dies of cardiac arrest"),
    (31, "Shah: Rs 4,000-cr Arunachal push"),
    (32, "Modi opens AI centre at IIT Patna"),
    (33, "Nvidia row: AI chips sent to China"),
    (34, "Lebanon seizes 264 kg of explosives"),
    (35, "Mosquitoes bred to fight dengue"),
    (36, "Anupama keeps world snooker crown"),
]


# ---- page layout -------------------------------------------------------
def draw_page(cv):
    cv.rect(0, 0, W, H, PAPER)

    # top band
    cv.rect(0, 0, W, 30, NAVY)
    draw_text(cv, 16, 8, "THE WORLD IN ONE DAY", WHITE, 2, bold=True)
    draw_text_right(cv, W - 16, 8, "36 STORIES - 7 REGIONS - EVERY ONE DATED",
                    WHITE, 2)

    # masthead date
    draw_text_center(cv, W // 2, 38, "Monday 23 November 2026", INK, 6,
                     bold=True)
    draw_text_center(cv, W // 2, 86,
                     "COP31 ends with no deal - Houthis hit Riyadh again "
                     "- BepiColombo reaches Mercury", RED, 2, bold=True)
    cv.hline(16, 108, W - 32, INK, 2)

    # stat strip
    col_w = (W - 32) // 6
    for i, (num, label) in enumerate(STATS):
        x = 16 + i * col_w
        if i:
            cv.vline(x - 4, 116, 48, (200, 192, 172))
        draw_text_center(cv, x + col_w // 2, 114, num, RED, 4, bold=True)
        draw_para(cv, x + 6, 146, label, INK, 1, col_w - 12)
    cv.hline(16, 168, W - 32, INK, 1)

    # region bar
    seg = (W - 32) // 7
    for i, (label, _count, color) in enumerate(REGIONS):
        x = 16 + i * seg
        w = seg if i < 6 else W - 32 - 6 * seg
        cv.rect(x, 172, w, 22, color)
        draw_text_center(cv, x + w // 2, 178, label, WHITE, 1)

    # the day in UTC
    draw_text(cv, 16, 202, "THE DAY", RED, 2, bold=True)
    draw_text(cv, 16, 218, "IN UTC", RED, 2, bold=True)
    draw_text(cv, 170, 202,
              "00:02 UTC - UN agrees to keep lethal-weapons talks going",
              INK, 2)
    draw_text(cv, 170, 218,
              "COP31 declared closed - Nepal PM meets Modi - ESA update due",
              INK, 2)
    cv.hline(16, 236, W - 32, INK, 1)

    # three lead stories
    lead_w, lead_gap = 320, 8
    for i, story in enumerate(LEADS):
        x = 16 + i * (lead_w + lead_gap)
        story["scene"](cv, x, 242, lead_w, 116)
        cv.frame(x, 242, lead_w, 116, INK, 1)
        cv.rect(x, 360, lead_w, 18, story["color"])
        draw_text(cv, x + 6, 364, story["kicker"], WHITE, 1)
        y = 384
        for line in wrap(story["headline"], 3, lead_w):
            draw_text(cv, x, y, line, INK, 3, bold=True)
            y += 22
        y += 6
        for line in wrap(story["body"], 2, lead_w):
            draw_text(cv, x, y, line, INK, 2)
            y += 16

    # twelve medium cards, 4 x 3
    card_w, card_h = 242, 88
    for i, story in enumerate(MEDIUM):
        col, row = i % 4, i // 4
        x = 16 + col * (card_w + 8)
        y = 508 + row * (card_h + 4)
        thumb_icon(cv, x, y, card_w, 26, story["icon"])
        draw_text(cv, x, y + 29, story["kicker"], RED, 1)
        yy = y + 40
        for line in wrap(story["headline"], 2, card_w):
            draw_text(cv, x, yy, line, INK, 2, bold=True)
            yy += 14
        draw_para(cv, x, y + 70, story["body"], INK, 1, card_w)

    # bottom: map left, in-brief right
    draw_text(cv, 16, 784, "WHERE IT HAPPENED", INK, 2, bold=True)
    draw_text(cv, 16, 802,
              "Schematic map - pins match story numbers. 3 BepiColombo: "
              "in orbit around Mercury.", GREY, 1)
    cell = 6
    mx, my = 30, 818
    for gy, rowstr in enumerate(MAP_ROWS):
        for gx, ch in enumerate(rowstr):
            if ch == '#':
                cv.rect(mx + gx * cell, my + gy * cell, cell - 1,
                        cell - 1, NAVY_LT)
    for num, (gx, gy) in PINS.items():
        cx, cy = mx + gx * cell + 3, my + gy * cell + 3
        cv.disc(cx, cy, 8, RED)
        cv.ring(cx, cy, 8, WHITE, 1)
        label = str(num)
        draw_text(cv, cx - text_w(label, 1) // 2, cy - 3, label, WHITE, 1)

    draw_text(cv, 512, 784, "IN BRIEF - 21 MORE STORIES", INK, 2, bold=True)
    draw_text(cv, 512, 802, "All reported 21-23 Nov - see the date check "
              "below.", GREY, 1)
    for j, (num, text) in enumerate(BRIEF):
        col = j // 11
        row = j % 11
        x = 512 + col * 252
        y = 818 + row * 11
        draw_text(cv, x, y, str(num), RED, 1, bold=True)
        draw_text(cv, x + 18, y, text, INK, 1)

    # date check + sources
    cv.frame(16, 956, W - 32, 32, RED, 2)
    draw_text(cv, 24, 962, "DATE CHECK - NOT COUNTED AS 23 NOV NEWS:",
              RED, 1, bold=True)
    draw_text(cv, 24, 974,
              "BepiColombo launched 2018 - COP31 opened 9 Nov - Gaza "
              "ceasefire Oct 2025 (background only) - the 2012 indictment "
              "behind the $5m reward.", INK, 1)
    draw_text(cv, 16, 992,
              "Sources: Reuters, BBC, AP, AFP, ESA, Al Jazeera, SCMP, WSJ, "
              "Detiknews - claims credited to those who made them. "
              "Pictures and map: original, drawn in code.", GREY, 1)

    # bottom band
    cv.rect(0, 1000, W, 24, NAVY)
    draw_text(cv, 16, 1006, "THE WORLD IN ONE DAY", WHITE, 2, bold=True)
    draw_text_right(cv, W - 16, 1006, "MONDAY 23 NOVEMBER 2026 - ONE PAGE",
                    WHITE, 2)


def main():
    here = Path(__file__).resolve().parent
    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    cv = Canvas(W, H, PAPER)
    draw_page(cv)
    data = png_bytes(cv)
    (out_dir / "entry.png").write_bytes(data)
    print("wrote %s (%d bytes, %dx%d)" % (out_dir / "entry.png",
                                          len(data), W, H))


if __name__ == "__main__":
    main()
