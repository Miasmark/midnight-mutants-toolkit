#!/usr/bin/env python3
"""
Turn captured terrain grids into maps.

tools/mame/grid.lua dumps $2400-$27E7 -- ten 100-cell bands -- every time the
screen changes. This resolves each cell through the area's property table the
way MapTileAt does (cell >> 1 indexes the table), trims the solid filler beyond
the playable region, and writes ASCII plus PNG.

Captures accumulate: run it over several grid.txt files and coverage grows.

Usage:
  python map2d.py grid.txt [more.txt ...] -o build/maps [--rom <rom.a78>]
"""
import argparse
import hashlib
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart

BANDS, CELLS = 10, 100

# tbl_AreaPtrLo/Hi at f7:$FEC7/$FED0 -- index 0 unused
AREA_PTR = [None, 0xDA00, 0xDA80, 0xDB00, 0xDB80, 0xDA80, 0xDA80, 0xDC00, 0xDC80]

# collision class -> glyph. Classes 1 and 2 each block one half of the cell
# diagonal, so they read as edges rather than walls.
GLYPH = {0: ".", 1: "/", 2: ":", 3: "#"}

# Event squares -- terrain with bit 7 set, dispatched by HandlePendingTerrain.
# Confirmed in play: $A0 is the well of health, the $8x codes are building and
# warp entrances, $EF is the final target.
EVENT_GLYPH = {0xA0: "W", 0xA1: "H", 0xEF: "X"}   # W well, H hurting ground
ITEM_GLYPH = "I"
def event_glyph(t):
    if t in EVENT_GLYPH:
        return EVENT_GLYPH[t]
    if 0x81 <= t <= 0x8F:
        return "E"          # scripted trigger: doorway, warp, cutscene
    if t >= 0xF0:
        return "F"          # handled at $5810
    return "?"

RGB = {".": (28, 26, 36), "/": (90, 84, 110), ":": (90, 84, 110),
       "#": (150, 142, 170),
       "E": (224, 131, 60),      # entrances / triggers
       "W": (90, 200, 150), "H": (200, 70, 110),
       "X": (230, 80, 80), "F": (200, 190, 90), "?": (255, 0, 255),
       "I": (250, 220, 90)}          # the item's authored position


def load(paths):
    caps = []
    for p in paths:
        lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
        for i, l in enumerate(lines):
            # src= is optional: grid.lua gained it partway through
            m = re.match(r"SCREEN (\S\S) area=(\S\S) page=(\S\S) ptr=(\S{4})"
                         r"(?: src=\S{4})? kind=(\S\S)"
                         r"(?: item=(\S\S))?(?: ipos=(\S{4}),(\S\S))?"
                         # grid4.lua adds the departure position: where the
                         # player stood the frame before the screen changed.
                         # The cross axis of that tells us which edge was used.
                         r"(?: from=(\S{4}),(\S\S),(\S\S) to=(\S{4}),(\S\S))?"
                         r"(?: defs=(\S+) kinds=(\S+))? frame=(\d+)", l)
            old = None
            if not m:
                old = re.match(r"SCREEN (\S\S) area=(\S\S) kind=(\S\S) frame=(\d+)", l)
            if not (m or old) or i + 1 >= len(lines):
                continue
            hexed = lines[i + 1].strip()
            if len(hexed) < BANDS * CELLS * 2:
                continue
            if m:
                caps.append({"screen": int(m.group(1), 16),
                             "area": int(m.group(2), 16),
                             "page": int(m.group(3), 16),
                             "ptr": int(m.group(4), 16),
                             "kind": int(m.group(5), 16),
                             "item": int(m.group(6), 16) if m.group(6) else None,
                             "ilong": int(m.group(7), 16) if m.group(7) else None,
                             "icross": int(m.group(8), 16) if m.group(8) else None,
                             "fromlong": int(m.group(9), 16) if m.group(9) else None,
                             "fromcross": int(m.group(10), 16) if m.group(10) else None,
                             # from= spans groups 9-11 and to= groups 12-13,
                             # so defs/kinds sit at 14/15
                             "defs": bytes.fromhex(m.group(14)) if m.group(14) else None,
                             "kinds": bytes.fromhex(m.group(15)) if m.group(15) else None,
                             "grid": bytes.fromhex(hexed[:BANDS * CELLS * 2])})
            else:
                caps.append({"screen": int(old.group(1), 16),
                             "area": int(old.group(2), 16),
                             "page": None, "ptr": None,
                             "kind": int(old.group(3), 16),
                             "grid": bytes.fromhex(hexed[:BANDS * CELLS * 2])})
    return caps


def resolve(cart, cap):
    """Grid bytes -> glyph rows, exactly as MapTileAt would read them."""
    # Use the pointer the machine actually had. Older captures fall back to
    # guessing from the area index, which is wrong for some areas.
    ptr = cap.get("ptr")
    if not ptr or not (0xD000 <= ptr < 0xE000):
        area = cap["area"]
        if not (1 <= area < len(AREA_PTR)) or AREA_PTR[area] is None:
            return None
        ptr = AREA_PTR[area]
    table = cart.slice("f7", ptr, 0x80)
    rows, events = [], {}
    for b in range(BANDS):
        band = cap["grid"][b * CELLS:(b + 1) * CELLS]
        row = ""
        for cell in band:
            terrain = table[(cell >> 1) & 0x7F]
            if terrain & 0x80:
                row += event_glyph(terrain)
                events[terrain] = events.get(terrain, 0) + 1
            else:
                row += GLYPH[terrain & 3]
        rows.append(row)
    return rows, events


def trim(rows):
    """Drop the solid filler beyond the playable region."""
    width = 0
    for r in rows:
        stripped = r.rstrip("#")
        width = max(width, len(stripped))
    width = min(CELLS, max(width + 2, 24))
    return [r[:width] for r in rows], width


def png(rows, path, scale=6):
    try:
        from PIL import Image
    except ImportError:
        return False
    h, w = len(rows), len(rows[0])
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            px[x, y] = RGB.get(ch, (0, 0, 0))
    img.resize((w * scale, h * scale), Image.NEAREST).save(path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    ap.add_argument("-o", "--out", default="build/maps")
    ap.add_argument("--rom", default="../Midnight Mutants/Midnight Mutants (NTSC) (Atari) (1990).a78")
    args = ap.parse_args()

    cart = Cart(args.rom)
    caps = load(args.captures)
    os.makedirs(args.out, exist_ok=True)

    # A grid is a complete area layout, not a window onto a longer strip:
    # measured across 72 capture pairs, grids at different screen indices are
    # either byte-identical or wholly different, never shifted. So deduplicate
    # by grid content and record which screen positions share each layout.
    layouts = {}
    dropped = 0
    for c in caps:
        # A capture taken while area_ptr was mid-update has a bogus pointer and
        # resolves through nonsense. Real property tables live in $DA00-$DCFF;
        # anything else is a timing artefact, not a place.
        ptr = c.get("ptr")
        if ptr is not None and not (0xD000 <= ptr < 0xE000):
            dropped += 1
            continue
        # Key on screen_kind_idx ($8A), NOT on the terrain grid. Grids are
        # reusable templates: $DA00's kinds $04/$05/$06/$0B are four different
        # rooms sharing one layout, distinguished only by kind (and confirmed in
        # play -- $0B holds a potion, the other three do not). Hashing the grid
        # merged them, which produced the contradiction of one room lying both
        # north and south of another. Keying on kind gives 62 rooms instead of
        # 51, no direction contradictions, and no room whose terrain differs
        # between visits -- kind -> terrain is a function.
        key = (ptr or c["area"], c["kind"])
        rec = layouts.setdefault(key, {"cap": c, "screens": set(),
                                       "items": set(), "kinds": set(), "defs": None})
        rec["screens"].add(c["screen"])
        rec["n"] = rec.get("n", 0) + 1      # how many captures back this layout
        # a layout is captured many times; keep whatever information any of
        # those captures happened to carry rather than only the first
        if c.get("item"):
            rec["items"].add(c["item"])
        if c.get("kinds"):
            rec["kinds"].update(k for k in c["kinds"] if k)
        if c.get("defs") and any(c["defs"]):
            rec["defs"] = c["defs"]

    doc = ["# Midnight Mutants -- terrain maps", "",
           "Captured from a running machine and resolved through each area's",
           "property table. `.` open, `/` and `:` block one half of the cell",
           "diagonal, `#` solid, `!` a scripted event square.", "",
           "One map per ROOM, keyed on `screen_kind_idx` ($8A). Terrain grids",
           "are shared templates -- $DA00 kinds $04/$05/$06/$0B are four",
           "different rooms drawn on one layout, and only $0B holds a potion --",
           "so keying on the grid merged places that are not the same place.", "",
           "Each map is the FULL scrolling field, not one screen. Rooms run up",
           "to seven screens along the long axis, and an exit's destination",
           "depends on how far along you leave it: quantised at 128 units,",
           "(room, edge, segment) determines the destination for 117 of 118",
           "observed transitions. Leaving the same field southward from the west",
           "end and from a screen further east lands you in different rooms.", "",
           "Captured when the area fill at `f7:$F243` finishes, so grids are",
           "coherent rather than caught mid-build. A layout is marked SUSPECT only",
           "if its event-cell count is implausibly high, which indicates the grid",
           "is not real terrain.", "",
           "Event squares are the interactive cells -- confirmed in play as",
           "building entrances, warps and the well of health:", "",
           "| glyph | meaning |", "|---|---|",
           "| `E` | scripted trigger `$81`-`$8F` -- doorway, warp, cutscene |",
           "| `W` | `$A0`, the well of health -- 1 health per tick |",
           "| `H` | `$A1`, hurting ground -- 2 health per tick |",
           "| `X` | `$EF`, the final target |",
           "| `F` | `$F0`+ |",
           "| `I` | the item's authored position |", ""]
    made = 0
    ITEM_CELLS = []
    per_area = defaultdict(int)
    for (grp, kind), rec in sorted(layouts.items(),
                                   key=lambda kv: (kv[0][0], kv[0][1])):
        cap, screens = rec["cap"], sorted(rec["screens"])
        area = cap["area"]
        got = resolve(cart, cap)
        if not got:
            continue
        rows, events = got
        # The item sits at an authored position in the area header. Convert it
        # the way MapTileAt converts the player: band from the cross axis,
        # cell from the long axis.
        placed = None
        il, ic = cap.get("ilong"), cap.get("icross")
        if il is not None and ic is not None and rec["items"]:
            # Calibrated against 24 known item placements plus three positions
            # identified in play: the player offsets MapTileAt uses ($0C, $18)
            # are wrong for items. -$04 on the cross axis and -$20 on the long
            # axis put 19 of 24 on open ground and only 3 inside walls.
            band = ((ic - 0x04) >> 4) & 0x0F
            cell = ((il - 0x20) >> 3)
            if 0 <= band < BANDS and 0 <= cell < CELLS:
                placed = (band, cell, rows[band][cell])
                rows[band] = rows[band][:cell] + ITEM_GLYPH + rows[band][cell+1:]
        rows, width = trim(rows)
        made += 1
        if placed:
            # An item on a table sits on a solid cell with walkable ground
            # below it, so "solid" alone does not mean misplaced.
            b, cl = placed[0], placed[1]
            below = rows[b + 1][cl] if b + 1 < len(rows) else "#"
            ITEM_CELLS.append((placed[2], below))
        per_area[grp] += 1
        # Name by kind rather than a sequential counter: kind is the game's own
        # room id, so a filename stays attached to the same room no matter what
        # order the captures arrive in or how many recordings are folded in.
        name = "tbl%04X_kind%02X" % (grp if grp > 255 else 0, kind)
        png(rows, os.path.join(args.out, name + ".png"))
        shown = ", ".join("$%02X" % s for s in screens[:12])
        if len(screens) > 12:
            shown += ", +%d more" % (len(screens) - 12)
        ev = "  ".join("$%02X x%d" % (t, n) for t, n in sorted(events.items()))
        extra = []
        nev = sum(events.values())
        if nev > 60:
            extra.append("**SUSPECT** -- %d event cells is far above any real room, "
                         "so this is probably not coherent terrain" % nev)
        extra.append("captures: %d" % rec.get("n", 0))
        if placed:
            extra.append("item at band %d cell %d (was `%s`)"
                         % (placed[0], placed[1], placed[2]))
        if rec["items"]:
            extra.append("items seen: " + ", ".join("`$%02X`" % i for i in sorted(rec["items"])))
        if rec["defs"]:
            d = rec["defs"]
            pairs = ["`$%02X`/`$%02X`" % (d[i], d[i+1])
                     for i in range(0, 12, 2) if d[i] or d[i+1]]
            if pairs:
                extra.append("enemy defs (amount/rate): " + ", ".join(pairs))
        if rec["kinds"]:
            extra.append("sactor kinds: " + ", ".join("`$%02X`" % k for k in sorted(rec["kinds"])))
        # Head the section with the room's own id, matching the PNG filename.
        # A sequential "layout N" counter did not, which made a section and its
        # image impossible to line up.
        doc += ["## `tbl%04X_kind%02X`  --  %d screen%s: %s"
                % (grp, kind, len(screens),
                   "" if len(screens) == 1 else "s", shown),
                "", "%d of %d cells shown" % (width, CELLS),
                "", "event squares: " + (ev or "none"),
                "", (" &middot; ".join(extra) if extra else ""), "", "```"]
        doc += rows
        doc += ["```", ""]

    with open(os.path.join(args.out, "MAPS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")
    print("%d captures -> %d distinct layouts (%d dropped: unsettled area_ptr)"
          % (len(caps), made, dropped))
    if ITEM_CELLS:
        walk = ".:/E"
        direct = sum(1 for ch, _ in ITEM_CELLS if ch in walk)
        ledge = sum(1 for ch, bl in ITEM_CELLS if ch not in walk and bl in walk)
        bad = len(ITEM_CELLS) - direct - ledge
        print("  item positions plotted: %d -- %d on walkable ground, %d on a "
              "ledge with floor below, %d unreachable"
              % (len(ITEM_CELLS), direct, ledge, bad))
    for a in sorted(per_area):
        print("   table $%04X: %d layouts" % (a, per_area[a]))
    print("wrote %s/MAPS.md and %d PNGs" % (args.out, made))


if __name__ == "__main__":
    main()
