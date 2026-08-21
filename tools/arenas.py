#!/usr/bin/env python3
"""
Render the three boss arenas out of the cartridge.

A boss fight does not load an area. `BossSetup` (`b5:$B013`) reads a 32-byte
record and blits directly into the character map at `$2400`, then the ordinary
display path draws it. The record's tail holds four groups of

    (source low, source high, column offset, destination row)

and `ArenaBlit` (`b5:$B141`) copies one of them. The source begins with a
four-byte header whose first two bytes are the width and height in characters;
the copy then walks `height` rows of `width` bytes, advancing the destination by
100 -- the character map's row stride -- each time.

Only one group per boss is populated. What it blits is not scenery: it is the
boss itself, a single large portrait pasted into the map. That is why a fight
bypasses the area loader entirely, and why `AREAS.md` has 76 rooms and no
arenas -- there is no room to describe.

Bank 5 is mapped throughout, so everything comes from it: the character sets at
CHARBASE `$80` and `$A0`, the tilemaps at `$9000`, and the code at `$B000`.

Usage:
  python arenas.py <rom.a78> -o build/arenas [--scale 2]
"""
import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart
from palette import ntsc7800
import rooms

TBL_SETUP_LO, TBL_SETUP_HI = 0xB19F, 0xB1A0
TBL_ARENA_PAL = 0xB207          # palette block pointers, by record byte +0
COLS, BANDS = 100, 10
CHAR_W, CHAR_H = 8, 16

BOSS = {1: "skull", 2: "ram", 3: "drevil"}


def record(cart, boss):
    return (cart.byte("b5", TBL_SETUP_LO + boss * 2)
            | (cart.byte("b5", TBL_SETUP_HI + boss * 2) << 8))


def arena_grid(cart, p):
    """Reproduce the blits into a 100x10 character grid."""
    grid = bytearray(COLS * BANDS)
    for g in range(4):
        lo, hi, off, row = [cart.byte("b5", p + 16 + g * 4 + k) for k in range(4)]
        if not hi:
            continue
        src = lo | (hi << 8)
        w, h = cart.byte("b5", src), cart.byte("b5", src + 1)
        src += 4                                    # past the four-byte header
        for y in range(h):
            for x in range(w):
                d = row * COLS + off + y * COLS + x
                if d < len(grid):
                    grid[d] = cart.byte("b5", src + y * w + x)
    return grid


def arena_palette(cart, pal_set):
    """Ten per-band palettes, same shape as an area's block."""
    ptr = (cart.byte("b5", TBL_ARENA_PAL + pal_set * 2)
           | (cart.byte("b5", TBL_ARENA_PAL + pal_set * 2 + 1) << 8))
    return [[ntsc7800(cart.byte("b5", ptr + b * 4 + k)) for k in (1, 2, 3)]
            for b in range(BANDS)]


def render(cart, boss, scale=2, trim=True):
    p = record(cart, boss)
    pal_set, charbase = cart.byte("b5", p), cart.byte("b5", p + 1)
    grid = arena_grid(cart, p)
    pal = arena_palette(cart, pal_set)
    cs = rooms.charset(cart, 5, charbase)

    img = Image.new("RGB", (COLS * CHAR_W, BANDS * CHAR_H), (0, 0, 0))
    px = img.load()
    for band in range(BANDS):
        for col in range(COLS):
            ch = grid[band * COLS + col]
            if not ch:
                continue
            for ln in range(CHAR_H):
                for half, byte in enumerate(cs[ch][ln]):
                    if not byte:
                        continue
                    for i in range(4):
                        v = (byte >> (6 - 2 * i)) & 3
                        if v:
                            px[col * CHAR_W + half * 4 + i,
                               band * CHAR_H + ln] = pal[band][v - 1]
    if trim:
        cols = [c for c in range(COLS)
                if any(grid[b * COLS + c] for b in range(BANDS))]
        if cols:
            img = img.crop(((min(cols) - 1) * CHAR_W, 0,
                            (max(cols) + 2) * CHAR_W, BANDS * CHAR_H))
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/arenas")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--full", action="store_true",
                    help="keep the whole 100-column map instead of trimming")
    args = ap.parse_args()
    cart = Cart(args.rom)
    os.makedirs(args.out, exist_ok=True)
    for boss, name in BOSS.items():
        img = render(cart, boss, args.scale, trim=not args.full)
        img.save(os.path.join(args.out, "%s.png" % name))
        print("boss %d %-7s -> %s.png  %dx%d" % (boss, name, name,
                                                 img.width, img.height))


if __name__ == "__main__":
    main()
