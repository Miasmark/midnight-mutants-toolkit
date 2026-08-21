#!/usr/bin/env python3
"""
A local ROM editor for Midnight Mutants: a small HTTP server over romedit.py,
driving a browser UI.

    python tools/editor.py "Midnight Mutants (NTSC) (Atari) (1990).a78"
    -> http://127.0.0.1:7800

Nothing leaves the machine and nothing is written until Save is pressed; the
loaded image is held in memory and every edit is a byte diff against the file
on disk, which the UI shows at all times.

The server hands the browser the raw material -- the character set, the palette
block and the 1000-byte grid -- and lets it draw.  That keeps painting instant
and means the render in the editor is the same one `rooms.py` produces, from
the same bytes, rather than a second implementation that could drift.
"""

import argparse
import base64
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import io
import bps
import mapgen
import music
import rooms
from palette import ntsc7800
from romedit import RomEdit, EditError

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "editor_ui")

ROM = None          # the live RomEdit
LOCK = threading.Lock()

# Regions are not room-number ranges -- they are a hand-made assignment in
# build/regions.json, the same one the rooms page uses, because the game's own
# grouping is scattered (the Mansion is $10 plus $41-$4F; the Shipwreck is $07,
# $12, $1F and $2F). Reading it here keeps the editor and the page in agreement
# instead of guessing from the kind number.
REGION_NAMES = {
    0x01: "Start & fields", 0x18: "Pumpkin fields", 0x33: "Woods & forest",
    0x3A: "Dr Evil", 0x41: "Mansion", 0x1C: "Lab / basement",
    0x22: "Caverns", 0x12: "Shipwreck", 0x1D: "Cabin & well", 0x11: "Cliffs",
}
REGION_ORDER = [0x01, 0x18, 0x33, 0x3A, 0x41, 0x1C, 0x22, 0x12, 0x1D, 0x11]
ASSIGN = {}


def load_regions():
    """room -> region key, from the same file the rooms page reads."""
    path = os.path.join(HERE, "..", "build", "regions.json")
    try:
        with open(path, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f)["assign"].items()}
    except Exception:
        return {}


def sprite_names():
    """Per-cell identifications for pages $C0 and $E0.

    build/_spritenames.py is the catalogue the sprite sheet was built from;
    each entry is tagged with how it was identified -- from the code, from
    play, or as a guess -- and that tag is passed through rather than hidden.
    """
    path = os.path.join(HERE, "..", "build", "_spritenames.py")
    ns = {}
    try:
        with open(path, encoding="utf-8") as f:
            exec(compile(f.read(), path, "exec"), ns)
    except Exception:
        return {}
    out = {}
    for page, key in ((0xC0, "C0"), (0xE0, "E0")):
        for low, val in (ns.get(key) or {}).items():
            name, how = val if isinstance(val, tuple) else (val, "")
            out["%02X:%02X" % (page, low)] = {"name": name, "how": how}
    return out


SPRITE_PAGES = [
    {"space": "f7", "page": 0xC0, "label": "$C0 player & zombies"},
    {"space": "f7", "page": 0xE0, "label": "$E0 creatures, items, Grampa"},
]


def region_of(kind):
    key = ASSIGN.get(kind)
    return REGION_NAMES.get(key, "Unassigned")


def region_rank(kind):
    key = ASSIGN.get(kind)
    return REGION_ORDER.index(key) if key in REGION_ORDER else len(REGION_ORDER)


def b64(data):
    return base64.b64encode(bytes(data)).decode("ascii")


def room_summary(kind):
    a = ROM.area(kind)
    it = ROM.item(kind)
    return {
        "kind": kind, "name": "$%02X" % kind, "region": region_of(kind),
        "segments": a["segments"], "bank": ROM.area_bank(kind),
        "dark": bool(a["dark"]), "item": it,
        "exits": sum(1 for v in a["north"] + a["south"] if v)
                 + (1 if a["west"] else 0) + (1 if a["east"] else 0),
    }


def item_icon(kind, pal):
    """The room item's icon as pixels, so the canvas can draw the real thing
    rather than a labelled box. Same character and palette choice the reference
    renderer makes in rooms.draw_icon."""
    it = ROM.item(kind)
    if not it:
        return None
    iid = it["id"]
    ch = ROM.byte("f6", rooms.TBL_ICON_COL + iid)
    if not ch:
        return None
    idx = ROM.byte("f6", rooms.TBL_ICON_PAL + iid) >> 5
    if idx == 6:
        # palette 6 is rewritten from the random generator every frame, so the
        # pumpkin and the diamond strobe. One frame of that stands in here.
        cols = rooms.flash_palette(0x4A)
    else:
        band = min(len(pal) - 1, max(0, it["y"] // rooms.CHAR_H))
        cols = rooms.base_palettes(ROM).get(idx) or pal[band]
    px = []
    for ln in range(rooms.CHAR_H):
        row = []
        base = (rooms.ICON_PAGE + (rooms.CHAR_H - 1 - ln)) << 8
        for half in (0, 1):
            try:
                byte = ROM.byte("f7", base | ((ch + half) & 0xFF))
            except Exception:
                byte = 0
            for i in range(4):
                v = (byte >> (6 - 2 * i)) & 3
                row.append(list(cols[v - 1]) if v else None)
        px.append(row)
    return {"id": iid, "char": ch, "palette": idx, "w": 8,
            "h": rooms.CHAR_H, "px": px, "flashes": idx == 6}


def boss_art_detail(n):
    """A boss portrait in the same shape the room canvas already understands:
    a character grid, the character set it indexes, and per-band palettes."""
    a = ROM.boss_art_view(n)
    return {
        "n": a["n"], "name": a["name"], "at": a["at"], "data": a["data"],
        "w": a["w"], "h": a["h"], "col": a["col"], "row": a["row"],
        "cells": a["cells"], "charset": b64(a["charset"]),
        "nchars": a["chars"], "cols": a["cols"], "bands": a["bands"],
        "charbase": a["charbase"], "pal_set": a["pal_set"],
        "record": a["record"],
        "palette": [[list(c) for c in band] for band in a["palette"]],
        "dirty": ROM.dirty(),
    }


def room_detail(kind):
    a = ROM.area(kind)
    bank = ROM.area_bank(kind)
    charbase, _ = rooms.area_gfx(ROM, a["page"])
    grid = ROM.grid(kind)
    # Two palettes: the lit one to edit against, and -- for a dark area -- the
    # collapsed one f7:$F134 actually produces, so the UI can show what a player
    # without the lantern sees. Holding the lantern clears area_is_dark
    # outright, so the lit view is also the with-lantern view.
    pal = ROM.palette_bands(a["stream"], 0)
    pal_dark = ROM.palette_bands(a["stream"], 1) if a["dark"] else None
    cs = rooms.charset(ROM, bank, charbase)

    # the character set as one flat blob: 128 chars x 16 lines x 2 bytes
    flat = bytearray()
    for ch in range(len(cs)):
        for ln in range(rooms.CHAR_H):
            flat += bytes(cs[ch][ln])

    offs = [ROM.byte("f7", mapgen.TBL_DST_OFF + x) for x in range(a["segments"])]
    width = max([o + 20 for o in offs] or [100])

    return {
        "kind": kind, "addr": a["addr"], "segments": a["segments"],
        "ids": a["ids"], "bank": bank, "charbase": charbase,
        "stream": a["stream"], "page": a["page"], "dark": bool(a["dark"]),
        "limit": a["limit"], "width": min(width, 100), "seg_offsets": offs,
        "nchars": len(cs),
        "grid": b64(grid), "charset": b64(flat),
        "palette": [[list(c) for c in band] for band in pal],
        "palette_dark": ([[list(c) for c in band] for band in pal_dark]
                         if pal_dark else None),
        "item": ROM.item(kind),
        "item_icon": item_icon(kind, pal),
        # one byte per (cell >> 1): the canvas overlays read collision from
        # bits 0-1, water from bit 2 and scripted tiles from bit 7
        "props": [ROM.byte("f7", ROM.prop_addr(a["page"]) + i)
                  for i in range(ROM.PROP_LEN)],
        "events": ROM.event_info(),
        "spawns": ROM.spawns(kind),
        "throwing": ROM.throwing(kind),
        "charset_rooms": len(ROM.charset_users(bank, charbase)),
        "palette_rooms": len(ROM.palette_users(a["stream"])),
        "palette_raw": ROM.read_palette(a["stream"]) if a["stream"] else None,
        "north": a["north"], "north_scr": a["north_scr"],
        "south": a["south"], "south_scr": a["south_scr"],
        "west": a["west"], "east": a["east"],
    }


def song_wav(n):
    """Render a song to a WAV using the same TIA model tools/music.py uses.

    It renders from the live edited image, not the file on disk, so a note
    changed a moment ago is what you hear.
    """
    class Live(music.Rom):
        def __init__(self, rom):
            self.hdr = 0
            self.raw = bytes(rom.rom)

    # music.py addresses its four tables by NTSC constant. Point them at this
    # image's copies for the duration of the render, then put them back, so a
    # European cartridge is synthesised from its own data rather than from
    # whatever sits three bytes earlier.
    tables = ("SONG_TABLE", "DUR_TABLE", "WAVE_BY_PITCH", "INSTR_TABLE")
    saved = {t: getattr(music, t) for t in tables}
    tmp = os.path.join(HERE, "..", "build", "_preview.wav")
    try:
        for t in tables:
            setattr(music, t, ROM.at("f6", saved[t]))
        music.render(Live(ROM), n, tmp, repeats=1)
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        for t in tables:
            setattr(music, t, saved[t])
        if os.path.exists(tmp):
            os.remove(tmp)
    return data


def health():
    """Every room must still parse. A bad header edit shows up here first."""
    bad = []
    for k in range(0x50):
        try:
            ROM.area(k)
        except EditError:
            pass
        except Exception as e:
            bad.append({"kind": k, "error": str(e)})
    return {"rooms": len(ROM.rooms()), "broken": bad}


def diff():
    ch = ROM.changes()
    return {
        "count": len(ch),
        "bytes": [{"off": o, "from": a, "to": b} for o, a, b in ch[:400]],
        "truncated": len(ch) > 400,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path.endswith((".js", ".css")):
            ctype = "text/javascript" if path.endswith(".js") else "text/css"
            return self._serve_file(os.path.basename(path), ctype)
        try:
            with LOCK:
                if path == "/api/rooms":
                    return self._send(200, {
                        "file": os.path.basename(ROM.path),
                        "version": ROM.version,
                        "rooms": [room_summary(k) for k in
                                  sorted(ROM.rooms(), key=lambda k: (region_rank(k), k))],
                        "dirty": ROM.dirty(),
                    })
                if path.startswith("/api/room/"):
                    return self._send(200, room_detail(int(path.rsplit("/", 1)[1], 16)))
                if path.startswith("/api/bossart/"):
                    return self._send(200, boss_art_detail(
                        int(path.rsplit("/", 1)[1])))
                if path.startswith("/api/grid/"):
                    k = int(path.rsplit("/", 1)[1], 16)
                    return self._send(200, {"grid": b64(ROM.grid(k)),
                                            "item": ROM.item(k),
                                            "dirty": ROM.dirty()})
                if path == "/api/toughness":
                    return self._send(200, {"kinds": ROM.toughness()})
                if path == "/api/rules":
                    return self._send(200, {"rules": ROM.rules()})
                if path == "/api/health-rules":
                    return self._send(200, ROM.health())
                if path == "/api/doors":
                    return self._send(200, ROM.doors())
                if path == "/api/songs":
                    return self._send(200, {"songs": ROM.songs()})
                if path.startswith("/api/songwav/"):
                    n = int(path.rsplit("/", 1)[1])
                    return self._send(200, song_wav(n), "audio/wav")
                if path == "/api/musictiming":
                    return self._send(200, dict(retick=ROM.music_retick(),
                                                **ROM.music_timing()))
                if path == "/api/pumpkinhint":
                    return self._send(200, ROM.pumpkin_hint())
                if path == "/api/pumpkinhint":
                    return self._send(200, ROM.pumpkin_hint())
                if path == "/api/actordeath":
                    return self._send(200, ROM.actor_death())
                if path == "/api/ghostdeath":
                    return self._send(200, ROM.ghost_death())
                if path == "/api/axefourth":
                    return self._send(200, ROM.axe_fourth())
                if path == "/api/megaframes":
                    return self._send(200, ROM.mega_frames())
                if path == "/api/axespin":
                    return self._send(200, ROM.axe_spin())
                if path == "/api/pickupshimmer":
                    return self._send(200, ROM.pickup_shimmer())
                if path == "/api/iconfixes":
                    return self._send(200, ROM.icon_fixes())
                if path == "/api/reticleleg":
                    return self._send(200, ROM.reticle_leg())
                if path == "/api/compactflip":
                    return self._send(200, ROM.compact_flip())
                if path == "/api/freespace":
                    return self._send(200, ROM.free_space())
                if path == "/api/waterwalk":
                    return self._send(200, ROM.water_walk())
                if path == "/api/debughook":
                    return self._send(200, ROM.debug_hook())
                if path == "/api/start":
                    return self._send(200, {"start": ROM.start_state()})
                if path == "/api/bossbox":
                    return self._send(200, {
                        "boxes": [ROM.boss_box(n) for n in (1, 2, 3)],
                        "ears": ROM.boss_ears(),
                        "art": [ROM.boss_art(n) for n in (1, 2, 3)]})
                if path == "/api/purity":
                    return self._send(200, {"sites": ROM.purity_drains(),
                                            "ladder": ROM.purity_necklace()})
                if path == "/api/sfxrefs":
                    return self._send(200, {"refs": ROM.sfx_refs()})
                if path == "/api/sfx":
                    return self._send(200, ROM.sfx_streams())
                if path == "/api/texts":
                    return self._send(200, {"texts": ROM.texts()})
                if path == "/api/bosses":
                    return self._send(200, ROM.bosses())
                if path == "/api/itemrefs":
                    return self._send(200, {"refs": ROM.item_refs(),
                                            "weapons": ROM.weapon_delays()})
                if path == "/api/spritepages":
                    return self._send(200, {"pages": SPRITE_PAGES,
                                            "names": sprite_names()})
                if path == "/api/blocks":
                    return self._send(200, {"blocks": ROM.blocks()})
                if path == "/api/ntsc":
                    # the whole 7800 colour space, once, for the picker
                    return self._send(200, {"rgb": [list(ntsc7800(v)) for v in range(256)]})
                if path == "/api/changes":
                    return self._send(200, diff())
                if path == "/api/health":
                    return self._send(200, health())
        except Exception as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "no such endpoint"})

    def _serve_file(self, name, ctype):
        p = os.path.join(UI, name)
        if not os.path.isfile(p):
            return self._send(404, {"error": name})
        with open(p, "rb") as f:
            self._send(200, f.read(), ctype)

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad JSON"})
        path = self.path.split("?")[0]
        try:
            with LOCK:
                return self._send(200, self._act(path, req))
        except EditError as e:
            return self._send(400, {"error": str(e), "refused": True})
        except bps.PatchError as e:
            return self._send(400, {"error": str(e), "refused": True,
                                    "patch": True})
        except Exception as e:
            return self._send(400, {"error": "%s: %s" % (type(e).__name__, e)})

    def _act(self, path, q):
        if path == "/api/paint":
            hits = []
            for c in q.get("cells") or [q]:
                hits.append(ROM.paint(int(q["kind"]), int(c["col"]),
                                      int(c["band"]), int(c["cell"])))
            affected = sorted({u["room"] for h in hits for u in h["also_affects"]})
            return {"ok": True, "slices": sorted({h["slice"] for h in hits}),
                    "also_affects": affected, "dirty": ROM.dirty()}
        if path == "/api/additem":
            ROM.add_item(int(q["kind"]), int(q["id"]))
            return {"ok": True, "item": ROM.item(int(q["kind"])), "dirty": ROM.dirty()}
        if path == "/api/removeitem":
            ROM.remove_item(int(q["kind"]))
            return {"ok": True, "item": ROM.item(int(q["kind"])), "dirty": ROM.dirty()}
        if path == "/api/item":
            ROM.set_item(int(q["kind"]), iid=q.get("id"), pending=q.get("pending"),
                         x=q.get("x"), y=q.get("y"))
            return {"ok": True, "item": ROM.item(int(q["kind"])), "dirty": ROM.dirty()}
        if path == "/api/spawn":
            ROM.set_spawn(int(q["kind"]), q["slot"], int(q["value"]))
            return {"ok": True, "spawns": ROM.spawns(int(q["kind"])),
                    "dirty": ROM.dirty()}
        if path == "/api/screenkind":
            ROM.set_screen_kind(int(q["kind"]), int(q["value"]))
            return {"ok": True, "spawns": ROM.spawns(int(q["kind"])),
                    "dirty": ROM.dirty()}
        if path == "/api/toughness":
            ROM.set_toughness(int(q["kind"]), int(q["seed"]))
            return {"ok": True, "kinds": ROM.toughness(), "dirty": ROM.dirty()}
        if path == "/api/pixel":
            ROM.set_char_pixel(int(q["bank"]), int(q["charbase"]), int(q["ch"]),
                               int(q["line"]), int(q["x"]), int(q["value"]))
            return {"ok": True, "rows": ROM.read_char(int(q["bank"]),
                    int(q["charbase"]), int(q["ch"])), "dirty": ROM.dirty()}
        if path == "/api/cell":
            return {"rows": ROM.read_cell(q["space"], int(q["page"]),
                                          int(q["low"]), int(q.get("width", 4)),
                                          int(q.get("lines", 16)))}
        if path == "/api/cellpixel":
            ROM.set_cell_pixel(q["space"], int(q["page"]), int(q["low"]),
                               int(q["x"]), int(q["line"]), int(q["value"]),
                               int(q.get("width", 4)), int(q.get("lines", 16)))
            return {"ok": True,
                    "rows": ROM.read_cell(q["space"], int(q["page"]),
                                          int(q["low"]), int(q.get("width", 4)),
                                          int(q.get("lines", 16))),
                    "dirty": ROM.dirty()}
        if path == "/api/char":
            return {"rows": ROM.read_char(int(q["bank"]), int(q["charbase"]),
                                          int(q["ch"])),
                    "rooms": ROM.charset_users(int(q["bank"]), int(q["charbase"]))}
        if path == "/api/blockcolour":
            ROM.set_block_colour(q["name"], int(q["index"]), int(q["slot"]),
                                 int(q["value"]))
            return {"ok": True, "blocks": ROM.blocks(), "dirty": ROM.dirty()}
        if path == "/api/palette":
            ROM.set_palette_colour(int(q["stream"]), int(q["band"]),
                                   int(q["index"]), int(q["value"]))
            return {"ok": True, "palette": ROM.read_palette(int(q["stream"])),
                    "dirty": ROM.dirty()}
        if path == "/api/itemref":
            ROM.set_item_ref(q["at"], int(q["item"]))
            return {"ok": True, "refs": ROM.item_refs(), "dirty": ROM.dirty()}
        if path == "/api/props":
            return ROM.properties(int(q["kind"]))
        if path == "/api/setprop":
            ROM.set_property(int(q["kind"]), int(q["index"]), int(q["value"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.properties(int(q["kind"])))
        if path == "/api/door":
            ROM.set_door(q["at"], int(q["dest"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.doors())
        if path == "/api/doorgate":
            ROM.set_door_gate(q["name"], int(q["value"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.doors())
        if path == "/api/setnote":
            ROM.set_note(q["space"], int(q["addr"]),
                         instrument=q.get("instrument"), dur=q.get("dur"),
                         wave=q.get("wave"), pitch=q.get("pitch"),
                         rest=q.get("rest"))
            return {"ok": True, "songs": ROM.songs(), "dirty": ROM.dirty()}
        if path == "/api/setmusicretick":
            ROM.set_music_retick(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), retick=ROM.music_retick(),
                        **ROM.music_timing())
        if path == "/api/setmusictiming":
            ROM.set_music_timing(bool(q["retime"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.music_timing())
        if path == "/api/setpumpkinhint":
            ROM.set_pumpkin_hint(bool(q["on"]), q.get("text"))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.pumpkin_hint())
        if path == "/api/setpumpkinhint":
            ROM.set_pumpkin_hint(bool(q["on"]), q.get("text"))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.pumpkin_hint())
        if path == "/api/setactordeath":
            ROM.set_actor_death(bool(q["fix"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.actor_death())
        if path == "/api/setghostdeath":
            ROM.set_ghost_death(bool(q["fix"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.ghost_death())
        if path == "/api/setaxefourth":
            ROM.set_axe_fourth(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.axe_fourth())
        if path == "/api/setmegaframes":
            ROM.set_mega_frames(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.mega_frames())
        if path == "/api/setaxespin":
            ROM.set_axe_spin(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.axe_spin())
        if path == "/api/setpickupshimmer":
            ROM.set_pickup_shimmer(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.pickup_shimmer())
        if path == "/api/seticonfixes":
            ROM.set_icon_fixes(bool(q["fix"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.icon_fixes())
        if path == "/api/setreticleleg":
            ROM.set_reticle_leg(bool(q["fix"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.reticle_leg())
        if path == "/api/setcompactflip":
            ROM.set_compact_flip(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.compact_flip())
        if path == "/api/setwaterwalk":
            ROM.set_water_walk(bool(q["on"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.water_walk())
        if path == "/api/setdebughook":
            ROM.set_debug_hook(bool(q["repair"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.debug_hook())
        if path == "/api/setstart":
            ROM.set_start(q["name"], int(q["value"]))
            return {"ok": True, "start": ROM.start_state(), "dirty": ROM.dirty()}
        if path == "/api/setbossbox":
            if q.get("shift") is not None:
                ROM.shift_boss_box(int(q["n"]), q["axis"], int(q["shift"]))
            else:
                ROM.set_boss_box(int(q["n"]), q["key"], int(q["value"]))
            return {"ok": True, "box": ROM.boss_box(int(q["n"])), "dirty": ROM.dirty()}
        if path == "/api/setbossear":
            ROM.set_boss_ear(q["key"], int(q["value"]))
            return {"ok": True, "ears": ROM.boss_ears(), "dirty": ROM.dirty()}
        if path == "/api/setbossart":
            n, v = int(q["n"]), int(q["value"])
            # a stroke can cover several cells; take a list or a single index
            idx = q["index"]
            for i in (idx if isinstance(idx, list) else [idx]):
                ROM.set_boss_art(n, int(i), v)
            a = ROM.boss_art(n)
            return {"ok": True, "art": a, "cells": a["cells"],
                    "dirty": ROM.dirty()}
        if path == "/api/setpurity":
            ROM.set_purity_drain(q["space"], int(q["addr"]), int(q["n"]))
            return {"ok": True, "sites": ROM.purity_drains(),
                    "ladder": ROM.purity_necklace(), "dirty": ROM.dirty()}
        if path == "/api/setpuritynecklace":
            ROM.set_purity_necklace(checks=q.get("checks"),
                                    without=q.get("without"))
            return {"ok": True, "sites": ROM.purity_drains(),
                    "ladder": ROM.purity_necklace(), "dirty": ROM.dirty()}
        if path == "/api/setsfxref":
            ROM.set_sfx_ref(q["space"], int(q["addr"]), int(q["id"]))
            return {"ok": True, "refs": ROM.sfx_refs(), "dirty": ROM.dirty()}
        if path == "/api/setsfx":
            ROM.set_sfx_stream(int(q["addr"]), q["bytes"])
            return dict(ok=True, dirty=ROM.dirty(), **ROM.sfx_streams())
        if path == "/api/setsfxptr":
            ROM.set_sfx_pointer(int(q["id"]), int(q["addr"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.sfx_streams())
        if path == "/api/settextparam":
            ROM.set_text_param(q["space"], int(q["addr"]), int(q["p2"]))
            return {"ok": True, "dirty": ROM.dirty()}
        if path == "/api/settextshimmer":
            ROM.set_text_shimmer(q["space"], int(q["addr"]), bool(q["shimmer"]))
            return dict(ok=True, dirty=ROM.dirty())
        if path == "/api/settext":
            ROM.set_text(q["space"], int(q["addr"]), q["text"])
            return {"ok": True, "texts": ROM.texts(), "dirty": ROM.dirty()}
        if path == "/api/boss":
            ROM.set_boss(int(q["n"]), q["field"], int(q["value"]))
            # same shape as the GET, so a caller can read one reply either way
            return dict(ok=True, dirty=ROM.dirty(), **ROM.bosses())
        if path == "/api/bosswin":
            ROM.set_boss_win(q["name"], int(q["value"]))
            return dict(ok=True, dirty=ROM.dirty(), **ROM.bosses())
        if path == "/api/healthrule":
            ROM.set_health(q["name"], int(q["value"]))
            return {"ok": True, "health": ROM.health(), "dirty": ROM.dirty()}
        if path == "/api/weapondelay":
            ROM.set_weapon_delay(int(q["level"]), int(q["delay"]))
            return {"ok": True, "weapons": ROM.weapon_delays(), "dirty": ROM.dirty()}
        if path == "/api/rule":
            ROM.set_rule(q["name"], int(q["value"]))
            return {"ok": True, "rules": ROM.rules(), "dirty": ROM.dirty()}
        if path == "/api/throwing":
            ROM.set_throwing(int(q["kind"]), int(q["value"]))
            return {"ok": True, "throwing": ROM.throwing(int(q["kind"])),
                    "dirty": ROM.dirty()}
        if path == "/api/exit":
            ROM.set_exit(int(q["kind"]), q["edge"], int(q["seg"]),
                         dest=q.get("dest"), arrive=q.get("arrive"))
            return {"ok": True, "dirty": ROM.dirty()}
        if path == "/api/field":
            ROM.set_area_field(int(q["kind"]), q["field"], int(q["value"]))
            return {"ok": True, "dirty": ROM.dirty()}
        if path == "/api/slicesel":
            ROM.set_slice_sel(int(q["kind"]), int(q["seg"]), int(q["sel"]))
            return {"ok": True, "dirty": ROM.dirty()}
        if path == "/api/sliceusers":
            return {"users": ROM.slice_users(int(q["bank"]), int(q["sel"]))}
        if path == "/api/revert":
            ROM.rom = bytearray(ROM.original)
            return {"ok": True, "dirty": False}
        if path == "/api/exportpatch":
            out = q.get("path") or os.path.join(
                os.path.dirname(os.path.abspath(ROM.path)),
                os.path.splitext(os.path.basename(ROM.path))[0] + ".bps")
            h = health()
            if h["broken"]:
                raise EditError("refusing to write a patch: %d rooms no longer "
                                "parse" % len(h["broken"]))
            return ROM.export_patch(out, q.get("note", ""))
        if path == "/api/patchinfo":
            return ROM.patch_info(q["path"])
        if path == "/api/importpatch":
            r = ROM.import_patch(q["path"], force=bool(q.get("force")))
            return dict(ok=True, dirty=ROM.dirty(), **r)
        if path == "/api/save":
            out = q.get("path") or os.path.join(
                os.path.dirname(os.path.abspath(ROM.path)),
                os.path.splitext(os.path.basename(ROM.path))[0] + " (edited).a78")
            h = health()
            if h["broken"]:
                raise EditError("refusing to save: %d rooms no longer parse"
                                % len(h["broken"]))
            size = ROM.save(out)
            return {"ok": True, "path": out, "size": size,
                    "changed": len(ROM.changes())}
        if path == "/api/segments":
            ROM.set_segments(int(q["kind"]), int(q["n"]), q.get("fill"))
            return {"ok": True, "room": room_summary(int(q["kind"])),
                    "free": [{"at": "f7:$%04X" % a, "bytes": n}
                             for n, a in ROM.f7_free(30)],
                    "dirty": ROM.dirty()}
        if path == "/api/disassemble":
            # Run the project's own disassembler over the edited image. Edits
            # are all in place, so the stock annotations still line up; PAL gets
            # its own file because its bank 6 and 7 are shifted.
            import subprocess
            import tempfile
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cfg = os.path.join(here, "annotations-pal.json"
                               if ROM.version == "pal" else "annotations.json")
            out = q.get("path") or os.path.join(
                os.path.dirname(os.path.abspath(ROM.path)),
                os.path.splitext(os.path.basename(ROM.path))[0] + " (disassembly)")
            os.makedirs(out, exist_ok=True)
            fd, tmp = tempfile.mkstemp(suffix=".a78")
            os.close(fd)
            try:
                ROM.save(tmp)
                cmd = [sys.executable,
                       os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "disasm.py"), tmp, "-o", out]
                if os.path.isfile(cfg):
                    cmd += ["-c", cfg]
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=300)
                if r.returncode:
                    raise EditError("the disassembler failed: %s"
                                    % (r.stderr or r.stdout or "")[-300:])
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            files = sorted(f for f in os.listdir(out) if f.endswith(".asm"))
            return {"ok": True, "path": out, "files": files,
                    "annotations": os.path.basename(cfg) if os.path.isfile(cfg)
                                   else None,
                    "version": ROM.version, "changed": len(ROM.changes())}
        raise EditError("no such endpoint: %s" % path)


def main():
    global ROM
    ap = argparse.ArgumentParser(description="GUI editor for a Midnight Mutants cartridge")
    ap.add_argument("rom")
    ap.add_argument("-p", "--port", type=int, default=7800)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    global ASSIGN
    ASSIGN = load_regions()
    ROM = RomEdit(args.rom)
    try:
        ROM.check_layout()
    except EditError as e:
        print("Refusing to open this cartridge.", file=sys.stderr)
        print("  %s" % e, file=sys.stderr)
        return 1
    n = len(ROM.rooms())
    url = "http://127.0.0.1:%d/" % args.port
    # flush explicitly: when this is launched from a .bat with its output
    # redirected, stdout is block-buffered and the URL would not appear until
    # the server stopped -- which is precisely when it is no longer useful.
    print("Midnight Mutants editor", flush=True)
    print("  cartridge : %s" % os.path.basename(args.rom), flush=True)
    print("  version   : %s" % ROM.version.upper(), flush=True)
    print("  rooms     : %d" % n, flush=True)
    print("  serving   : %s     (ctrl-c to stop)" % url, flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.%s" % ("  UNSAVED EDITS WERE DISCARDED." if ROM.dirty() else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
