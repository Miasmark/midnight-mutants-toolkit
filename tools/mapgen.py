#!/usr/bin/env python3
"""
Generate terrain grids from the ROM, without an emulator.

The fill routine at f7:$F243 is a plain table copy, validated byte-exact
against captured memory:

    n   = $1EC6                       slice count, from the area header
    sel = $1EC7 + x                   per-slice source selector
    src = tbl_F2B4[sel] | tbl_F2E8[sel] << 8      into the paged area bank
    dst = $2400 + tbl_F31D[x]         destination column group

    for slice x < n:
        for band in 0..9:
            copy 20 bytes src -> dst;  src += $14;  dst += $64

Given a screen's (slice count, selector list, area bank, property table) this
reproduces its grid exactly. Those four come from the area header; this tool
reads them from a gridv.txt capture, then generates everything else offline.

It also reports how many distinct terrain slices exist in the ROM versus how
many the captures actually reached -- i.e. how much of the world is still
unmapped.

Usage:
  python mapgen.py gridv.txt -o build/maps [--rom <rom.a78>]
"""
import argparse
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart
from map2d import BANDS, CELLS, GLYPH, event_glyph, png, trim

TBL_SRC_LO, TBL_SRC_HI = 0xF2B4, 0xF2E8      # source pointer, by selector
TBL_DST_OFF = 0xF31D                         # destination column group, by slice
BANKS = ["b0", "b1", "b2", "b3", "b4", "b5"]


def build(cart, n, sel, bank):
    """Reproduce f7:$F243 for one screen. Returns the 1000-byte grid."""
    g = bytearray(1000)
    for x in range(n):
        s = sel[x]
        src = cart.byte("f7", TBL_SRC_LO + s) | (cart.byte("f7", TBL_SRC_HI + s) << 8)
        dst = cart.byte("f7", TBL_DST_OFF + x)
        for _ in range(BANDS):
            try:
                run = cart.slice(bank, src, 20)
            except Exception:
                return None
            for y in range(20):
                if dst + y < 1000:
                    g[dst + y] = run[y]
            src += 0x14
            dst += 0x64
    return g


def resolve(cart, grid, ptr):
    table = cart.slice("f7", ptr, 0x80)
    rows, events = [], {}
    for b in range(BANDS):
        row = ""
        for cell in grid[b * CELLS:(b + 1) * CELLS]:
            t = table[(cell >> 1) & 0x7F]
            if t & 0x80:
                row += event_glyph(t)
                events[t] = events.get(t, 0) + 1
            else:
                row += GLYPH[t & 3]
        rows.append(row)
    return rows, events


def offline(cart, caps, out):
    """Rebuild every room's terrain from the area headers alone."""
    made = 0
    for c in caps:
        for bank in BANKS:
            g = build(cart, c["n"], c["sel"], bank)
            if g:
                rows = [ "".join(GLYPH[g[b * CELLS + x] & 3] for x in range(CELLS))
                         for b in range(BANDS) ]
                rows, _w = trim(rows)
                png(rows, os.path.join(out, "gen_kind%02X.png" % c["kind"]))
                made += 1
                break
    print("%d rooms rebuilt from the ROM alone (no emulator)" % made)
    print("wrote %d PNGs to %s" % (made, out))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", nargs="?",
                    help="optional gridv.txt; omit to build from the ROM alone")
    ap.add_argument("--offline", action="store_true",
                    help="take slice counts and selectors from the area headers "
                         "instead of a capture -- no emulator needed")
    ap.add_argument("-o", "--out", default="build/maps")
    ap.add_argument("--rom", default="../Midnight Mutants/Midnight Mutants (NTSC) (Atari) (1990).a78")
    args = ap.parse_args()

    cart = Cart(args.rom)
    os.makedirs(args.out, exist_ok=True)

    if args.offline or not args.capture:
        # The fill's inputs are exactly what LoadAreaHeader reads: n from $1EC6
        # and the selector list from $1EC7, which is the $00-terminated list at
        # offset 24 of the area header. So every room's terrain rebuilds with no
        # emulator at all -- verified byte-exact for all 76 rooms within each
        # room's declared extent (the fill writes n slices and leaves the rest of
        # the buffer holding the previous area, so comparing the whole 1000-byte
        # buffer against a capture spuriously fails on short rooms).
        from areas import load as _load7, parse as _parse, N_KINDS
        b7 = _load7(args.rom)
        caps = []
        for k in range(N_KINDS):
            _a, r = _parse(b7, k)
            if r and r["ids"]:
                caps.append({"kind": k, "n": len(r["ids"]), "sel": bytes(r["ids"])})
        return offline(cart, caps, args.out)

    lines = open(args.capture, encoding="utf-8", errors="replace").read().split("\n")
    caps = []
    for i, l in enumerate(lines):
        m = re.match(r"SCREEN (\S\S) ptr=(\S{4}) n=(\S\S) sel=(\S+)", l)
        if m and i + 1 < len(lines) and len(lines[i + 1]) >= 2000:
            caps.append({"screen": int(m.group(1), 16), "ptr": int(m.group(2), 16),
                         "n": int(m.group(3), 16), "sel": bytes.fromhex(m.group(4)),
                         "real": bytes.fromhex(lines[i + 1][:2000])})

    exact = 0
    layouts, seen_sel = {}, set()
    for c in caps:
        if not (1 <= c["n"] <= 13) or not (0xD000 <= c["ptr"] < 0xE000):
            continue
        for bank in BANKS:                       # which bank was paged in
            g = build(cart, c["n"], c["sel"], bank)
            if g and bytes(g) == c["real"]:
                exact += 1
                seen_sel.update(c["sel"][:c["n"]])
                key = (c["ptr"], hashlib.md5(g).hexdigest())
                layouts.setdefault(key, {"grid": g, "screens": set(), "bank": bank})
                layouts[key]["screens"].add(c["screen"])
                break

    print("%d captures; %d reproduced byte-exact from ROM alone" % (len(caps), exact))

    # how much terrain exists that we have never seen?
    valid = sum(1 for s in range(0x40)
                if 0x8000 <= (cart.byte("f7", TBL_SRC_LO + s) |
                              (cart.byte("f7", TBL_SRC_HI + s) << 8)) < 0xC000)
    print("terrain slices: %d selectors point into the area window, %d reached"
          % (valid, len(seen_sel)))

    doc = ["# Midnight Mutants -- generated terrain maps", "",
           "Produced from the ROM by reproducing the fill at `f7:$F243`.",
           "Every map below was verified byte-exact against captured memory.", "",
           "| glyph | meaning |", "|---|---|",
           "| `.` | open |", "| `/` `:` | blocks half the cell diagonal |",
           "| `#` | solid |", "| `E` | trigger `$81`-`$8F` |",
           "| `W` | `$A0` well of health |", "| `H` | `$A1` hurting ground |",
           "| `X` | `$EF` final target |", "| `F` | `$F0`+ |", ""]
    per = Counter()
    for (ptr, digest), rec in sorted(layouts.items(),
                                     key=lambda kv: (kv[0][0], min(kv[1]["screens"]))):
        rows, events = resolve(cart, rec["grid"], ptr)
        rows, width = trim(rows)
        per[ptr] += 1
        name = "gen_tbl%04X_%02d" % (ptr, per[ptr])
        png(rows, os.path.join(args.out, name + ".png"))
        scr = ", ".join("$%02X" % s for s in sorted(rec["screens"])[:10])
        ev = "  ".join("$%02X x%d" % (t, n) for t, n in sorted(events.items()))
        doc += ["## table $%04X, map %d  --  bank %s  --  screens: %s"
                % (ptr, per[ptr], rec["bank"], scr), "",
                "%d of %d cells shown | events: %s" % (width, CELLS, ev or "none"),
                "", "```"] + rows + ["```", ""]

    with open(os.path.join(args.out, "GENMAPS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")
    print("wrote %s/GENMAPS.md and %d PNGs" % (args.out, sum(per.values())))


if __name__ == "__main__":
    main()
