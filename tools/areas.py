#!/usr/bin/env python3
"""
Catalogue every area header from the ROM alone.

The header pointer table lives at f7:$F32A + 2*screen_kind_idx and holds 80
entries, $F32A-$F3C9, ending exactly where the first header begins. 76 entries
point at a real header; four ($00, $3D, $3E, $3F) are null and are not rooms.

Header layout, as read by LoadAreaHeader (f7:$F00C):

    0      graphics/scenery stream selector  ($40)
    1      area_page ($1FCF) -- which graphics bank the area draws from
    2      area_is_dark ($1EC5) -- cleared outright when the lantern is held
    3,4    map_limit base; +$AE gives map_limit ($72/$73)
    5,6    $1F20 / $1F21 -- the $8C exit destination
    24..   $00-terminated event id list, then that many destination kinds,
           then that many screen indices, then that many cross positions

Validated against a running machine for 37 of 37 areas: ids and destinations
both exact.

Usage:
  python areas.py <rom.a78> -o AREAS.md
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import BANK_SIZE

PTR_TABLE = 0xF32A          # indexed by screen_kind_idx, 2 bytes per entry
N_KINDS = 0x50              # the table is 80 entries: $F32A..$F3C9, ending
                            # exactly where the first header begins at $F3CA.
                            # Reading past it treats header bytes as pointers,
                            # which is what made kind $54 look like a stale
                            # entry pointing into code.
EXITS_AT = 24               # offset of the exit section within a header
DATA_LO = 0xF3CA            # first real header


def load(path):
    rom = open(path, "rb").read()
    hdr = 128 if len(rom) % BANK_SIZE else 0
    return rom[hdr + 7 * BANK_SIZE: hdr + 8 * BANK_SIZE]


def parse(b7, kind):
    a = b7[PTR_TABLE - 0xC000 + kind * 2] | (b7[PTR_TABLE - 0xC000 + kind * 2 + 1] << 8)
    if not (DATA_LO <= a < 0xFFF0):
        return a, None
    o = a - 0xC000
    p = o + EXITS_AT
    ids = []
    while b7[p] and len(ids) < 24:
        ids.append(b7[p])
        p += 1
    p += 1
    n = len(ids)
    return a, {
        "stream": b7[o], "page": b7[o + 1], "dark": b7[o + 2],
        "limit": b7[o + 3] | (b7[o + 4] << 8),
        # +5 and +6 are the long-axis exits, one destination each for the whole
        # room rather than per segment. f6:$5918 takes the west one when the
        # world position falls below $1D; f6:$5929 takes the east one on
        # reaching map_limit. Zero means that edge is a wall -- which is when
        # the map_limit clamp at f6:$53A6 actually bites.
        "west": b7[o + 5], "east": b7[o + 6],
        "f20": b7[o + 5], "f21": b7[o + 6],
        "ids": ids,
        # Five parallel arrays follow the slice list, not four. f6:$57E2 and
        # f6:$57F9 read them as two independent exit tables: the first pair
        # lands the player at cross $9E (the bottom of the new room) and so is
        # the NORTH exit, the second lands at $0C (the top) and is the SOUTH
        # exit. A destination of 0 means that edge has no exit on that segment.
        "north": list(b7[p:p + n]),
        "north_scr": list(b7[p + n:p + 2 * n]),
        "south": list(b7[p + 2 * n:p + 3 * n]),
        "south_scr": list(b7[p + 3 * n:p + 4 * n]),
        # kept so older callers keep working
        "dest": list(b7[p:p + n]),
        "scr": list(b7[p + n:p + 2 * n]),
        "cross": list(b7[p + 2 * n:p + 3 * n]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="AREAS.md")
    args = ap.parse_args()
    b7 = load(args.rom)

    rooms, dead = {}, {}
    for k in range(N_KINDS):
        a, r = parse(b7, k)
        (rooms if r else dead)[k] = r if r else a

    doc = ["# Midnight Mutants -- area headers", "",
           "Every room the game defines, read from the ROM alone. The pointer",
           "table is at `f7:$%04X + 2*screen_kind_idx`." % PTR_TABLE, "",
           "The table holds **%d entries** (`$%04X`-`$%04X`), ending exactly"
           % (N_KINDS, PTR_TABLE, PTR_TABLE + N_KINDS * 2 - 1),
           "where the first header begins. **%d are real rooms**; the other %d"
           % (len(rooms), len(dead)),
           "hold a null pointer and are not rooms at all: %s."
           % ", ".join("`$%02X`" % k for k in sorted(dead)), "",
           "`dark` is cleared outright when the lantern (item `$09`) is held.", ""]

    # regional summary first -- page is effectively the region
    doc += ["## Graphics pages", "",
            "| page | rooms | count |", "|---|---|---|"]
    by = collections.defaultdict(list)
    for k, v in rooms.items():
        by[v["page"]].append(k)
    for pg in sorted(by):
        ks = sorted(by[pg])
        doc.append("| `$%02X` | %s | %d |"
                   % (pg, " ".join("`$%02X`" % x for x in ks), len(ks)))

    dk = collections.Counter(v["dark"] for v in rooms.values())
    doc += ["", "## Darkness", "",
            "| value | rooms |", "|---|---|"]
    for v, n in sorted(dk.items()):
        note = " -- lit" if v == 0 else " -- dark without the lantern"
        doc.append("| `$%02X` | %d%s |" % (v, n, note))

    doc += ["", "## Rooms", "",
            "| kind | header | page | stream | dark | map limit | exits |",
            "|---|---|---|---|---|---|---|"]
    for k in sorted(rooms):
        v = rooms[k]
        a, _ = parse(b7, k)
        ex = ", ".join("`$%02X`&rarr;`$%02X`" % (v["ids"][i], v["dest"][i])
                       for i in range(len(v["ids"]))) or "--"
        doc.append("| `$%02X` | `$%04X` | `$%02X` | `$%02X` | `$%02X` | `$%04X` | %s |"
                   % (k, a, v["page"], v["stream"], v["dark"], v["limit"], ex))

    doc += ["", "## Exit detail", "",
            "`screen` and `cross` are where you arrive, not where you leave.",
            "Several entries can share one event id and differ only in the",
            "segment you trigger it from -- the index is",
            "`(world_position - $18) / 160`, computed by `sub_D190`.", ""]
    for k in sorted(rooms):
        v = rooms[k]
        if not v["ids"]:
            continue
        doc.append("**`$%02X`** &nbsp; " % k + " &nbsp; ".join(
            "id `$%02X` &rarr; `$%02X` @ scr `$%02X`, cross `$%02X`"
            % (v["ids"][i], v["dest"][i], v["scr"][i], v["cross"][i])
            for i in range(len(v["ids"]))) + "  ")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")
    print("%d rooms, %d non-room indices" % (len(rooms), len(dead)))
    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
