#!/usr/bin/env python3
"""
Render the actor sprites out of the cartridge as individual cells.

MARIA stores graphics line-planar: with a display-list entry pointing at
(high << 8) | low, scanline n of the zone reads page high+n at the same low
byte. So a sprite that is W bytes wide and H lines tall occupies

    page high+0 .. high+H-1,  bytes low .. low+W-1

The actors write $E0 into the display entry's high byte (a few write $C0), so
their artwork lives at f7:$E000 and f7:$C000. In 160x2 mode each byte is four
2-bit pixels, so a 4-byte cell is 16 pixels wide.

Colour is chosen at run time from the MARIA palette registers -- the actors use
palette $BE -- so this renders the raw 2-bit indices as four levels rather than
inventing colours. Index 0 is transparent and is left as the page background.

Usage:
  python sprites.py <rom.a78> -o build/sprites [--page E0] [--lines 16]
"""
import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import BANK_SIZE

# The four 2-bit indices. 0 is transparent; the rest are rendered as a light
# ramp so the artwork reads on either page background.
LEVEL = [None, (120, 116, 140), (188, 184, 205), (245, 243, 250)]


def bank7(path):
    rom = open(path, "rb").read()
    hdr = 128 if len(rom) % BANK_SIZE else 0
    return rom[hdr + 7 * BANK_SIZE: hdr + 8 * BANK_SIZE]


def cell(b7, page, low, width, lines):
    """One sprite: width bytes x lines scanlines, line-planar.

    MARIA's zone offset counts DOWN: the first scanline of a zone reads the
    highest page and the last reads the base. Rendering pages in ascending order
    turns every sprite upside down -- the giveaway is the lettering on page $E0,
    where $D8/$DC spell GAME and $F8/$FC spell OVER only when flipped.
    """
    px = Image.new("RGBA", (width * 4, lines), (0, 0, 0, 0))
    p = px.load()
    for ln in range(lines):
        base = ((page + (lines - 1 - ln)) << 8) - 0xC000
        for bx in range(width):
            off = base + low + bx
            if not (0 <= off < len(b7)):
                continue
            byte = b7[off]
            for i in range(4):
                v = (byte >> (6 - 2 * i)) & 3
                if LEVEL[v] is not None:
                    p[bx * 4 + i, ln] = LEVEL[v] + (255,)
    return px


def nonempty(img):
    return any(px[3] for px in img.getdata())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/sprites")
    ap.add_argument("--page", default="E0")
    ap.add_argument("--lines", type=int, default=16)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--scale", type=int, default=4)
    args = ap.parse_args()

    b7 = bank7(args.rom)
    page = int(args.page, 16)
    os.makedirs(args.out, exist_ok=True)

    made = []
    for low in range(0, 256, args.width):
        img = cell(b7, page, low, args.width, args.lines)
        if not nonempty(img):
            continue
        w, h = img.size
        img = img.resize((w * args.scale, h * args.scale), Image.NEAREST)
        name = "s_%02X_%02X.png" % (page, low)
        img.save(os.path.join(args.out, name))
        made.append((low, name))

    print("page $%02X: %d non-empty cells of %d bytes x %d lines"
          % (page, len(made), args.width, args.lines))
    print("wrote %s" % args.out)
    return made


if __name__ == "__main__":
    main()
