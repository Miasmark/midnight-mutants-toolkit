#!/usr/bin/env python3
"""
Render each room as the game actually draws it -- terrain, charset and colour --
straight from the cartridge, with no emulator and no capture.

Everything needed comes from the area header (`dat_F32A`, indexed by
screen_kind_idx) plus three tables in bank 7:

    header +0            palette block index  -> dat_D44B -> 40 bytes
    header +1            area index 0-8
    header +2            area_is_dark
    header +24           $00-terminated slice selector list

    tbl_AreaPage $FEB5   area index -> CHARBASE
    tbl_AreaBank $FEBE   area index -> ROM bank paged into $8000

The slice selector list is the same list `areas.py` reports as exit `ids`: a
room's terrain slices and its exit segments are one and the same, which is why
an exit is identified by a scroll segment.

MARIA character mode forms a character's graphics address as

    ((CHARBASE + (height - 1 - line)) << 8) | character

so a charset is line-planar. CTRL is $50: read mode 00 (160x2) with bit 4 set,
which makes characters **two bytes wide** -- MARIA fetches the map byte and the
one after it, giving 8 pixels. A zone is 16 scanlines tall.

Two independent checks agree on that width. A terrain slice is 20 characters and
an exit segment is 160 world units, which only reconciles at 8 pixels per
character; and every non-zero character number in the game -- 30,874 of them --
is even, exactly as a byte addressing a 2-byte pair must be.

The grid is 100 characters wide by 10 bands, so a full room is 800 x 160 pixels,
five screens wide, because a room scrolls.

The 40-byte palette block is ten groups of four, one per band: a leading byte
then three colour bytes. Index 0 is transparent and shows the background.

Usage:
  python rooms.py <rom.a78> -o build/rooms
  python rooms.py <rom.a78> --kind 01 -o build/rooms --scale 3
"""
import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:
    # Only the PNG writers below need imaging. The editor imports this module
    # for charset/palette/geometry and draws in the browser, so it must be able
    # to load without Pillow installed.
    Image = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart
import areas
import mapgen
from palette import ntsc7800, PLAY_PALETTE, flash_palette

# Palettes 2-5 are never reloaded when an area is entered. Exactly two block
# copies write them in the whole ROM: b3:$81C9 during the intro, and b0:$A581
# when the Grampa screen opens. Whichever ran last is what the world shows, and
# since the inventory screen is opened constantly, the Grampa block is the live
# one in normal play -- it is the one with a blue palette 3.
INTRO_PAL_BLOCK = 0x81C9        # b3, loaded once during the intro
GRAMPA_PAL_BLOCK = 0xA581       # b0, loaded every time the inventory opens


def base_palettes(cart, intro=False):
    """MARIA palettes 0-7, as the copy loops load them.

    Both loops walk X from $20 down and store block[X] into register $20+X,
    skipping every fourth slot, so palette n's three colours sit at offsets
    1 + n*4. Item icons carry their palette index in the top three bits of
    tbl_ItemIconPal.
    """
    if intro:
        blk = [cart.byte("b3", INTRO_PAL_BLOCK + i) for i in range(32)]
    else:
        blk = [cart.byte("b0", GRAMPA_PAL_BLOCK + i) for i in range(32)]
    return {n: [ntsc7800(blk[1 + n * 4 + i]) for i in range(3)] for n in range(8)}

TBL_AREA_PROP_LO = 0xFEC7       # area index -> terrain property table
TBL_AREA_PROP_HI = 0xFED0
TBL_AREA_PAGE = 0xFEB5          # area index -> CHARBASE
TBL_AREA_BANK = 0xFEBE          # area index -> ROM bank at $8000
TBL_PAL_BLOCK = 0xD44B          # palette block pointers, by header +0
TBL_ICON_COL = 0x5195           # f6: item id -> character number on page $E0
TBL_ICON_PAL = 0x51A5           # f6: item id -> palette|width byte
ICON_PAGE = 0xE0                # item icons live on page $E0 in bank 7

COLS, BANDS = 100, 10           # the character grid
CHAR_W, CHAR_H = 8, 16          # one character in pixels (two bytes wide)


def area_gfx(cart, idx):
    """(CHARBASE, ROM bank) for an area index."""
    return cart.byte("f7", TBL_AREA_PAGE + idx), cart.byte("f7", TBL_AREA_BANK + idx)


def palette_block(cart, pal_idx, dark=0):
    """Ten per-band palettes of three colours, as RGB triples.

    `area_is_dark` collapses every colour the same way f7:$F134 does -- keep
    bit 3 and shift it down twice, so the whole area falls to $00 or $02.
    """
    lo = cart.byte("f7", TBL_PAL_BLOCK + pal_idx * 2)
    hi = cart.byte("f7", TBL_PAL_BLOCK + pal_idx * 2 + 1)
    ptr = lo | (hi << 8)
    if ptr < 0xC000:
        return None
    bands = []
    for b in range(BANDS):
        cols = []
        for c in range(1, 4):
            v = cart.byte("f7", ptr + b * 4 + c)
            if dark:
                v = (v & 0x08) >> 2
            cols.append(ntsc7800(v))
        bands.append(cols)
    return bands


def charset(cart, bank, charbase):
    """All 256 characters as [char][line] -> (byte, byte), read line-planar.

    CTRL is $50, so bit 4 (CWIDTH) is set: characters are **two bytes wide**,
    and MARIA fetches the map byte and the one after it. At 160x2 that is eight
    pixels per character, which is what makes a 20-character terrain slice
    exactly the 160 world units of one exit segment. Reading one byte per
    character instead renders half of every tile at half width -- the artwork
    survives well enough to look like terrain, which is what makes the mistake
    easy to miss.
    """
    space = "b%d" % bank
    out = []
    for ch in range(256):
        lines = []
        for ln in range(CHAR_H):
            # the zone offset counts DOWN: line 0 reads the highest
            # page and the last line reads CHARBASE itself. Same rule
            # as the sprites -- see SPRITES.md.
            base = (charbase + (CHAR_H - 1 - ln)) << 8
            pair = []
            for off in (ch, (ch + 1) & 0xFF):
                try:
                    pair.append(cart.byte(space, base | off))
                except Exception:
                    pair.append(0)
            lines.append(pair)
        out.append(lines)
    return out


def item_of(cart, b7, addr):
    """(id, pending, x, y) in pixels for the room's item, or None.

    Header +7 is item_type: low seven bits the id, bit 7 meaning the item is
    pending until the room is cleared.

    The position is two separate coordinates, not one packed offset. Header +22
    is scaled by eight at f7:$F1C4 to give the long-axis pixel position, which
    DrawItemIcon then offsets by the scroll. Header +23 goes to $1E7D and is the
    cross-axis position in pixels -- the same value the pickup test subtracts at
    f6:$51DF.
    """
    it = b7[addr - 0xC000 + 7]
    if not it:
        return None
    # $18 is the world-origin bias that the exit model also carries -- an exit
    # segment is (world_position - $18) / 160 -- so the same subtraction turns a
    # world x into a position within the rendered room.
    # The pickup test at f6:$51C0 collects when the player sits in
    # [item_x - 7, item_x + 2], so item_x is the icon's right side, not its
    # left. Back off one character to get the left edge.
    x = ((b7[addr - 0xC000 + 22] * 8) & 0x7FF) - 0x18 - CHAR_W
    y = b7[addr - 0xC000 + 23]
    return it & 0x7F, bool(it & 0x80), x, y


def draw_icon(px, cart, item_id, ox, oy, colours, w, h):
    """Stamp the item's icon into an already-rendered room at pixel (ox, oy)."""
    ch = cart.byte("f6", TBL_ICON_COL + item_id)
    if not ch:
        return
    for ln in range(CHAR_H):
        base = (ICON_PAGE + (CHAR_H - 1 - ln)) << 8
        for half in (0, 1):
            try:
                byte = cart.byte("f7", base | ((ch + half) & 0xFF))
            except Exception:
                continue
            for i in range(4):
                v = (byte >> (6 - 2 * i)) & 3
                if not v:
                    continue
                x, y = ox + half * 4 + i, oy + ln
                if 0 <= x < w and 0 <= y < h:
                    px[x, y] = colours[v - 1]


def render(cart, kind, b7, scale=2, lit=False, items=True):
    if Image is None:
        raise RuntimeError("rendering to PNG needs Pillow:  pip install Pillow")
    try:
        addr, a = areas.parse(b7, kind)
    except Exception:
        return None
    if not a:
        return None
    idx = a["page"]
    charbase, bank = area_gfx(cart, idx)
    grid = mapgen.build(cart, len(a["ids"]), a["ids"], "b%d" % bank)
    if grid is None:
        return None
    # `lit` renders a dark area as if the lantern were held: without it the
    # collapse at f7:$F134 makes the caves genuinely, correctly black.
    pal = palette_block(cart, a["stream"], 0 if lit else a["dark"])
    if pal is None:
        return None
    cs = charset(cart, bank, charbase)

    # a room is only as wide as its slices: each covers 20 columns, placed by
    # tbl_F31D. Anything past that is grid that the fill never touched.
    width = COLS
    used = 0
    for x in range(len(a["ids"])):
        used = max(used, cart.byte("f7", mapgen.TBL_DST_OFF + x) + 20)
    if 0 < used <= COLS:
        width = used

    img = Image.new("RGB", (width * CHAR_W, BANDS * CHAR_H), (0, 0, 0))
    px = img.load()
    for band in range(BANDS):
        colours = pal[band]
        for col in range(width):
            ch = grid[band * COLS + col]
            if not ch:
                continue
            glyph = cs[ch]
            for ln in range(CHAR_H):
                y = band * CHAR_H + ln
                for half, byte in enumerate(glyph[ln]):
                    if not byte:
                        continue
                    for i in range(4):
                        v = (byte >> (6 - 2 * i)) & 3
                        if v:
                            px[col * CHAR_W + half * 4 + i, y] = colours[v - 1]
    if items:
        got = item_of(cart, b7, addr)
        if got:
            iid, pending, ix, iy = got
            idx = cart.byte("f6", TBL_ICON_PAL + iid) >> 5
            if idx == 6:
                # palette 6 has no fixed value: f6:$4C70 rewrites all three of
                # its registers from the random generator every frame, so the
                # diamond strobes. One frame of that stands in here.
                cols = flash_palette(0x4A)
            else:
                cols = (base_palettes(cart).get(idx)
                        or pal[min(BANDS - 1, max(0, iy // CHAR_H))])
            # the cross coordinate is the icon's baseline, not its centre
            draw_icon(px, cart, iid, ix, iy - CHAR_H, cols,
                      width * CHAR_W, BANDS * CHAR_H)

    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="build/rooms")
    ap.add_argument("--kind")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--lit", action="store_true",
                    help="render dark areas as if the lantern were held")
    args = ap.parse_args()

    cart = Cart(args.rom)
    b7 = areas.load(args.rom)
    os.makedirs(args.out, exist_ok=True)

    kinds = [int(args.kind, 16)] if args.kind else range(areas.N_KINDS)
    made = 0
    for kind in kinds:
        img = render(cart, kind, b7, args.scale, args.lit)
        if img is None:
            continue
        img.save(os.path.join(args.out, "room_%02X.png" % kind))
        made += 1
    print("rendered %d rooms to %s" % (made, args.out))


if __name__ == "__main__":
    main()


# Terrain codes with bit 7 set are scripted squares rather than ground. The
# dispatch at f6:$5776 handles $A0, $8C, $8E and $8F; $F0 and up go to $5810,
# which turns them into a boss entry gated on boss_flags.
EVENTS = {
    0x81: "door", 0x82: "gated door", 0x83: "door", 0x84: "gated door",
    0x85: "gated door", 0x86: "gated door", 0x90: "door",
    0x8C: "door west", 0x8E: "door south", 0x8F: "door north",
    0xA0: "well", 0xA1: "hurting ground", 0xEF: "the win",
    0xF1: "BOSS door: Skull", 0xF2: "BOSS door: Ram", 0xF3: "BOSS door: Dr Evil",
}


def event_cells(cart, b7, kind):
    """[(code, band, col)] for every scripted square in the room.

    The grid holds character numbers; the terrain code comes from the area's
    property table, indexed by (cell >> 1) & $7F -- so two adjacent characters
    share one terrain property.

    All three boss doors are here statically -- Skull in $1E, Ram in $15, Dr Evil
    in $3C. An earlier version of this scan walked the grid as one flat run
    instead of 10 bands of 100, which missed most cells and made it look as
    though only the Ram's door existed.
    """
    addr, a = areas.parse(b7, kind)
    if not a:
        return []
    idx = a["page"]
    bank = cart.byte("f7", TBL_AREA_BANK + idx)
    ptr = (cart.byte("f7", TBL_AREA_PROP_LO + idx)
           | (cart.byte("f7", TBL_AREA_PROP_HI + idx) << 8))
    if not (0xC000 <= ptr < 0xFFF0):
        return []
    grid = mapgen.build(cart, len(a["ids"]), a["ids"], "b%d" % bank)
    if grid is None:
        return []
    table = cart.slice("f7", ptr, 0x80)
    width = len(a["ids"]) * 20
    out = []
    for band in range(BANDS):
        for col in range(width):
            t = table[(grid[band * COLS + col] >> 1) & 0x7F]
            if t & 0x80:
                out.append((t, band, col))
    return out
