#!/usr/bin/env python3
"""
Extract Midnight Mutants' text.

The game stores dialogue as plain uppercase ASCII in records shaped

    $FF <p1> <p2> '@' <text bytes> '#'

with these control codes inside the text (confirmed against the renderer at
b0:$A22F-$A2D1 and the terminator test at f7:$D398):

    '@' $40  start of text
    '#' $23  end of text
    '|' $7C  newline      -- renderer adds $16 (22) to the destination pointer,
                             so the text window is 22 columns wide
    '&' $26  new page     -- resets the column ($65) then does a newline
    '*' $2A  draws glyph $3C in place of a character
    '^' $5E  apostrophe

Usage: python text.py <rom.a78> [-o TEXT.md] [--raw]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart, BANK_SIZE

CTRL = {0x7C: "\n", 0x26: "\n\n[NEW PAGE]\n", 0x5E: "'", 0x2A: "*"}


def window(cart, b):
    if b == cart.fixed_lo:
        return 0x4000, "f6"
    if b == cart.fixed_hi:
        return 0xC000, "f7"
    return 0x8000, "b%d" % b


def decode(raw):
    out = []
    for c in raw:
        if c in CTRL:
            out.append(CTRL[c])
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
        else:
            out.append("\\x%02X" % c)
    return "".join(out)


def records(data):
    """Yield (hdr_off, p1, p2, text_off, raw_text) for every $FF ?? ?? '@' record."""
    i = 0
    while i < len(data) - 4:
        if data[i] == 0xFF and data[i + 3] == 0x40:
            end = data.find(b"#", i + 4)
            if 0 < end - (i + 4) < 1024:
                yield i, data[i + 1], data[i + 2], i + 4, data[i + 4:end]
                i = end + 1
                continue
        i += 1


PRINTABLE = set(range(0x20, 0x7F)) | {0x7C, 0x5E, 0x26, 0x2A}


def records_b(data, minlen=10):
    """Yield records in the second framing, used by the credits/cutscene pool.

    Shape is `<$FE|$FF> <p1> <p2>` followed by the text, running to the next
    $FE or $FF.  No '@' introducer and no '#' terminator, so it needs its own
    scan; see the credits block at f6:$73F7.
    """
    i = 0
    while i < len(data) - 4:
        if data[i] in (0xFE, 0xFF):
            j = i + 3
            k = j
            while k < len(data) and data[k] in PRINTABLE:
                k += 1
            if k - j >= minlen and k < len(data) and data[k] in (0xFE, 0xFF):
                yield i, data[i + 1], data[i + 2], j, data[j:k]
                i = k
                continue
        i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="TEXT.md")
    ap.add_argument("--blocks", help="write JSON data-block list here")
    args = ap.parse_args()

    cart = Cart(args.rom)
    out = ["# Midnight Mutants -- text records", "",
           "Record format `$FF <p1> <p2> '@' text '#'`.  Control codes are decoded;",
           "`[NEW PAGE]` is `&` ($26) and newlines are `|` ($7C).", ""]
    blocks = []
    total = 0
    for b in range(cart.nbanks):
        data = cart.rom[b * BANK_SIZE:(b + 1) * BANK_SIZE]
        base, space = window(cart, b)
        def keep(r):
            return sum(1 for c in r[4] if 0x41 <= c <= 0x5A) > len(r[4]) * 0.4

        recs = [(r, "A") for r in records(data) if keep(r)]
        covered = set()
        for r, _ in recs:
            covered.update(range(r[0], r[3] + len(r[4]) + 1))
        recs += [(r, "B") for r in records_b(data)
                 if keep(r) and r[0] not in covered]
        recs.sort(key=lambda t: t[0][0])
        if not recs:
            continue
        total += len(recs)
        out += ["## bank %d (`%s`, mapped at $%04X) -- %d records"
                % (b, space, base, len(recs)), ""]
        for (hdr, p1, p2, toff, raw), kind in recs:
            out += ["### `$%04X`  p1=$%02X p2=$%02X  (%d bytes, framing %s)"
                    % (base + hdr, p1, p2, len(raw), kind), "", "```",
                    decode(bytes(raw)), "```", ""]
            blocks.append({"loc": "%s:%04X" % (space, base + hdr),
                           "end": "%s:%04X" % (space, base + toff + len(raw)
                                               + (1 if kind == "A" else 0)),
                           "type": "text",
                           "name": "txt%s_%04X" % (space[1:], base + hdr)})
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("wrote %s (%d records)" % (args.out, total))
    if args.blocks:
        import json
        with open(args.blocks, "w") as f:
            json.dump(blocks, f, indent=2)
        print("wrote %s (%d blocks)" % (args.blocks, len(blocks)))


if __name__ == "__main__":
    main()
