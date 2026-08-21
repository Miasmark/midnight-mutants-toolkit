#!/usr/bin/env python3
"""
The write side of the cartridge: a mutable Cart plus structured accessors for
the data the disassembly identified.

Everything here edits **in place**.  The ROM is a fixed 128K with no slack --
an area bank's window is 98% claimed by known readers, area headers are packed
end to end, and the only free run anyone has found is 111 bytes in bank 6.  So
no accessor is allowed to change the size of anything: lists keep their length,
records keep their layout, and a write that would need more room is refused
rather than silently shifting whatever follows it.

Two facts shape the whole design:

  * **Terrain slices are shared.**  39 slices cover 76 rooms, so painting one
    room repaints every other room that draws the same slice.  `slice_users`
    reports that blast radius before anything is written.
  * **A header's segment count is structural.**  The $00-terminated slice list
    sets `n`, and five parallel arrays of length `n` follow it.  Changing how
    many entries it has would move the four arrays after it and run into the
    next header, so the count is fixed and only values may change.

Usage:
  python romedit.py <rom.a78>            audit: parse everything, verify no-op
"""

import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart, BANK_SIZE
import areas
import bps
import mapgen
import rooms
from reloc import relocate, detect

BANDS, COLS = 10, 100
SLICE_LEN = 200                 # 10 bands of 20 cells
EXITS_AT = areas.EXITS_AT       # 24
PTR_TABLE = areas.PTR_TABLE     # f7:$F32A


class EditError(Exception):
    """A write was refused because it would not fit or would move data."""


class RomEdit(Cart):
    """A Cart that can be written to and saved, tracking every change."""

    def __init__(self, path):
        Cart.__init__(self, path)
        self.rom = bytearray(self.rom)
        self.original = bytes(self.rom)
        self.path = path
        # Which release this image is. Every address in this file is the NTSC
        # one; the European cartridge moves bank 6 by +3 and part of bank 7 by
        # +9 for its taller display list. Rather than mapping at each call site,
        # the address tables themselves are relocated once here, so the
        # accessors below are identical for both.
        #
        # Addresses read *out of* the ROM -- area headers, slice pointers,
        # palette block pointers, boss records -- are already correct for the
        # image and are deliberately not touched.
        self.version = detect(self) or "ntsc"
        self._relocate()

    def at(self, space, addr):
        """An NTSC address, in this cartridge's layout."""
        return relocate(self.version, space, addr)

    def _relocate(self):
        if self.version == "ntsc":
            return
        cls = type(self)
        for name in ("TBL_AMOUNT", "TBL_RATE", "TBL_SCREEN_KIND", "TBL_TOUGHNESS",
                     "WEAPON_DELAY", "PAL_TBL", "TBL_PROP_LO", "TBL_PROP_HI",
                     "BOSS_PTRS", "BOSS_CONTACT"):
            space = "f6" if name in ("TBL_SCREEN_KIND", "TBL_TOUGHNESS",
                                     "WEAPON_DELAY") else "f7"
            if name in ("BOSS_PTRS", "BOSS_CONTACT"):
                space = "b5"
            setattr(self, name, self.at(space, getattr(cls, name)))
        # tables whose rows carry their own space and address
        self.RULES = [(n, sp, self.at(sp, ad)) + tuple(rest)
                      for n, sp, ad, *rest in cls.RULES]
        self.HEALTH = [(n, sp, self.at(sp, ad)) + tuple(rest)
                       for n, sp, ad, *rest in cls.HEALTH]
        self.START = [(n, sp, self.at(sp, ad)) + tuple(rest)
                      for n, sp, ad, *rest in cls.START]
        self.BOSS_WIN = [(n, sp, self.at(sp, ad)) + tuple(rest)
                         for n, sp, ad, *rest in cls.BOSS_WIN]
        self.ITEM_REFS = [(sp, self.at(sp, ad)) + tuple(rest)
                          for sp, ad, *rest in cls.ITEM_REFS]
        self.DOORS = [(code, sp, self.at(sp, ad)) + tuple(rest)
                      for code, sp, ad, *rest in cls.DOORS]
        self.DOOR_GATES = [(n, sp, self.at(sp, ad)) + tuple(rest)
                           for n, sp, ad, *rest in cls.DOOR_GATES]
        self.DEBUG_FIX = [(self.at("b0", ad),) + tuple(rest)
                          for ad, *rest in cls.DEBUG_FIX]

    # ---------------------------------------------------------------- bytes
    def check_layout(self):
        """Both known releases are supported; anything else is refused."""
        if detect(self) is None:
            raise EditError(
                "this cartridge matches neither the NTSC nor the European "
                "layout, so the addresses this editor uses cannot be placed. "
                "See VERSIONS.md.")

    def offset(self, space, addr):
        return self.bank_of(space) * BANK_SIZE + (addr - self.base_of(space))

    def poke(self, space, addr, data):
        """Write bytes at a CPU address in a space. Never grows the image."""
        if isinstance(data, int):
            data = bytes([data])
        off = self.offset(space, addr)
        if not (0 <= off and off + len(data) <= len(self.rom)):
            raise EditError("write at %s:$%04X falls outside the image" % (space, addr))
        if not self.in_space(space, addr + len(data) - 1):
            raise EditError("write at %s:$%04X crosses out of the bank window"
                            % (space, addr))
        self.rom[off:off + len(data)] = data

    def changes(self):
        """Every differing byte, as (rom offset, before, after)."""
        return [(i, self.original[i], self.rom[i])
                for i in range(len(self.rom)) if self.original[i] != self.rom[i]]

    def dirty(self):
        return self.rom != self.original

    def save(self, out):
        blob = (self.header or b"") + bytes(self.rom)
        with open(out, "wb") as f:
            f.write(blob)
        return len(blob)

    # --------------------------------------------------------------- areas
    def b7(self):
        return bytes(self.rom[self.fixed_hi * BANK_SIZE:(self.fixed_hi + 1) * BANK_SIZE])

    def area_addr(self, kind):
        b = self.b7()
        o = PTR_TABLE - 0xC000 + kind * 2
        return b[o] | (b[o + 1] << 8)

    def rooms(self):
        """Every kind that resolves to a real header, in order."""
        b, out = self.b7(), []
        for k in range(areas.N_KINDS):
            _, a = areas.parse(b, k)
            if a:
                out.append(k)
        return out

    def area(self, kind):
        addr, a = areas.parse(self.b7(), kind)
        if not a:
            raise EditError("kind $%02X is not a room" % kind)
        a["addr"] = addr
        a["segments"] = len(a["ids"])
        return a

    # The five parallel arrays start right after the terminated slice list.
    def _arrays_at(self, kind):
        a = self.area(kind)
        return a["addr"] + EXITS_AT + a["segments"] + 1, a["segments"]

    def set_area_field(self, kind, field, value):
        """Set a scalar header byte. Structural fields are refused."""
        if field == "limit":
            # Two bytes at +3/+4. LoadAreaHeader adds $AE, so this is the base
            # rather than the limit the clamp at f6:$53A6 compares against.
            v = int(value) & 0xFFFF
            base = self.area(kind)["addr"]
            self.poke("f7", base + 3, bytes([v & 0xFF, v >> 8]))
            return
        off = {"stream": 0, "page": 1, "dark": 2, "west": 5, "east": 6}
        if field not in off:
            raise EditError("%r is not an editable scalar field" % field)
        self.poke("f7", self.area(kind)["addr"] + off[field], value & 0xFF)

    def set_slice_sel(self, kind, seg, sel):
        """Point one of a room's segments at a different terrain slice."""
        a = self.area(kind)
        if not 0 <= seg < a["segments"]:
            raise EditError("segment %d out of range (room has %d)" % (seg, a["segments"]))
        self.poke("f7", a["addr"] + EXITS_AT + seg, sel & 0xFF)

    # ---------------------------------------------------- the room's own width
    # A header is 25 + 5n bytes: 24 scalars, a $00-terminated list of n slice
    # ids, then four parallel n-entry exit arrays. So the segment count *is*
    # the room's width, and changing it resizes the record.
    #
    # The records cannot grow where they sit. They are packed with no slack and
    # five of them deliberately overlap: room $10's header begins three bytes
    # inside room $0F's last exit array, sharing them. Editing a tail in place
    # would silently rewrite the next room's stream, page and dark flag.
    #
    # They can move instead. Every header is found through the pointer table at
    # f7:$F32A, never by walking, so a record may live anywhere in bank 7 --
    # and relocating one leaves its original bytes untouched, which is exactly
    # what an overlapping neighbour needs.
    AREA_BLOCK = (0xF3CA, 0xFEB5)      # where the shipped headers sit
    # f7:$F243 lays each segment 20 columns into the 100x10 map at $2400, so
    # five is the buffer exactly. The shipped rooms agree: 14 of them use five
    # and none uses more. A sixth would wrap into the next band and its final
    # row would overrun $27E7 into score_digits.
    MAX_SEGMENTS = 5

    def area_span(self, kind):
        return 25 + 5 * self.area(kind)["segments"]

    def f7_free(self, need):
        """Runs of $00 a header could live in, largest first.

        Not anywhere in bank 7: areas.parse only accepts a pointer at $F3CA or
        above, so a header placed lower would load on the machine but stop
        being a room to every tool in this project. The usable space is
        therefore what sits above the shipped block.
        """
        lo, hi = self.AREA_BLOCK
        out, run, start = [], 0, None
        for a in range(lo, 0xFFF0):
            if self.byte("f7", a) == 0 and not (lo <= a < hi):
                if not run:
                    start = a
                run += 1
            else:
                if run >= need:
                    out.append((run, start))
                run = 0
        if run >= need:
            out.append((run, start))
        out.sort(reverse=True)
        return out

    def read_area_record(self, kind):
        a = self.area(kind)
        n = a["segments"]
        base = a["addr"]
        return {"head": [self.byte("f7", base + i) for i in range(EXITS_AT)],
                "ids": list(a["ids"]),
                "north": list(a["north"]), "north_scr": list(a["north_scr"]),
                "south": list(a["south"]), "south_scr": list(a["south_scr"]),
                "n": n, "addr": base, "span": 25 + 5 * n,
                "relocated": not (self.AREA_BLOCK[0] <= base < self.AREA_BLOCK[1])}

    def _pack_area(self, rec, n, fill):
        def fit(seq, pad):
            seq = list(seq[:n])
            return seq + [pad] * (n - len(seq))
        out = list(rec["head"])
        out += fit(rec["ids"], fill) + [0x00]
        for key in ("north", "north_scr", "south", "south_scr"):
            out += fit(rec[key], 0)
        return bytes(out)

    def set_segments(self, kind, n, fill=None):
        """Change how many segments -- how wide -- a room is.

        New segments repeat the room's last slice unless `fill` names one, and
        arrive with no vertical exits. The record is rewritten somewhere free
        rather than in place, so nothing that overlaps the old bytes moves.
        """
        n = int(n)
        if not 1 <= n <= self.MAX_SEGMENTS:
            raise EditError(
                "a room can have 1 to %d segments. The map builder at "
                "f7:$F243 writes each one 20 columns into a 100x10 buffer at "
                "$2400, so five fill it exactly; a sixth starts at column 100, "
                "which is the second band, and its last row runs past $27E7 "
                "over score_digits" % self.MAX_SEGMENTS)
        rec = self.read_area_record(kind)
        if n == rec["n"]:
            return
        if fill is None:
            fill = rec["ids"][-1] if rec["ids"] else 0x01
        if not fill:
            raise EditError("a slice id of $00 would terminate the list early")
        body = self._pack_area(rec, n, fill)
        here = rec["addr"]
        home = getattr(self, "_area_home", None)
        if home is None:
            home = self._area_home = {}
        # Returning to the shipped width should go home rather than leave a
        # copy stranded in the tail.
        wrote = getattr(self, "_area_wrote", None)
        if wrote is None:
            wrote = self._area_wrote = {}

        def release(addr):
            self.poke("f7", addr, bytes(wrote.pop(addr, rec["span"])))

        back = home.get(kind)
        if back is not None:
            # count the way the loader does: stop at the $00 terminator,
            # because the exit arrays after it are not slice ids
            was = 0
            while was < 24 and self.byte("f7", back + EXITS_AT + was):
                was += 1
            if n == was:
                # Write the record back, not just the pointer: anything edited
                # while it was away lives in the copy, and at the shipped width
                # it fits its old slot exactly.
                release(here)
                self.poke("f7", back, body)
                self.poke("f7", self.at("f7", PTR_TABLE) + 2 * kind,
                          bytes([back & 0xFF, back >> 8]))
                del home[kind]
                return
        if rec["relocated"] and len(body) <= rec["span"]:
            at = here                        # already outside the block: reuse
        else:
            runs = self.f7_free(len(body))
            if not runs:
                raise EditError("no run of %d free bytes in bank 7 -- a %d "
                                "segment header needs that much and the "
                                "shipped block has none to give"
                                % (len(body), n))
            at = runs[0][1]
            if rec["relocated"]:
                release(here)                               # give the old back
            else:
                home[kind] = here                           # so it can go back
        self.poke("f7", at, body)
        wrote[at] = max(wrote.get(at, 0), len(body))
        self.poke("f7", self.at("f7", PTR_TABLE) + 2 * kind,
                  bytes([at & 0xFF, at >> 8]))

    def set_exit(self, kind, edge, seg, dest=None, arrive=None):
        """Set a per-segment vertical exit. `edge` is 'north' or 'south'."""
        base, n = self._arrays_at(kind)
        if edge not in ("north", "south"):
            raise EditError("edge must be north or south")
        if not 0 <= seg < n:
            raise EditError("segment %d out of range (room has %d)" % (seg, n))
        row = 0 if edge == "north" else 2
        if dest is not None:
            self.poke("f7", base + row * n + seg, dest & 0xFF)
        if arrive is not None:
            self.poke("f7", base + (row + 1) * n + seg, arrive & 0xFF)

    # -------------------------------------------------------------- terrain
    def slice_addr(self, sel):
        b = self.b7()
        return (b[mapgen.TBL_SRC_LO - 0xC000 + sel]
                | (b[mapgen.TBL_SRC_HI - 0xC000 + sel] << 8))

    def area_bank(self, kind):
        return rooms.area_gfx(self, self.area(kind)["page"])[1]

    def read_slice(self, bank, sel):
        return bytes(self.slice("b%d" % bank, self.slice_addr(sel), SLICE_LEN))

    def write_slice(self, bank, sel, data):
        if len(data) != SLICE_LEN:
            raise EditError("a slice is exactly %d bytes, got %d" % (SLICE_LEN, len(data)))
        self.poke("b%d" % bank, self.slice_addr(sel), bytes(data))

    def slice_users(self, bank, sel):
        """Which rooms in this bank draw a slice -- the blast radius of editing it."""
        out = []
        for k in self.rooms():
            a = self.area(k)
            if self.area_bank(k) != bank:
                continue
            for seg, s in enumerate(a["ids"]):
                if s == sel:
                    out.append({"room": k, "segment": seg})
        return out

    def grid(self, kind):
        """The assembled 100x10 character grid, exactly as f7:$F243 builds it."""
        a = self.area(kind)
        return mapgen.build(self, a["segments"], a["ids"], "b%d" % self.area_bank(kind))

    def paint(self, kind, col, band, cell):
        """Set one grid cell, resolving which slice and offset actually back it.

        Returns the write's blast radius so a caller can warn before committing.
        """
        a = self.area(kind)
        bank = self.area_bank(kind)
        for seg in range(a["segments"]):
            dst = self.byte("f7", mapgen.TBL_DST_OFF + seg)
            if dst <= col < dst + 20:
                sel = a["ids"][seg]
                data = bytearray(self.read_slice(bank, sel))
                data[band * 20 + (col - dst)] = cell & 0xFF
                self.write_slice(bank, sel, data)
                return {"slice": sel, "bank": bank,
                        "also_affects": [u for u in self.slice_users(bank, sel)
                                         if u["room"] != kind]}
        raise EditError("column %d is outside this room's %d segments"
                        % (col, a["segments"]))

    # --------------------------------------------------------------- actors
    # Six placement budgets, one byte each. ExpandAreaDef (f7:$F280) splits a
    # byte into a high nibble indexing tbl_DefAmount and a low nibble indexing
    # tbl_DefRateMask -- so one byte says how many and how often. The rate mask
    # is the reciprocal of the rate: $00 fires every frame, $FF is rare.
    DEFS = [(9, "def0", "crow"), (8, "def1", "bat"), (10, "def2", "wolf"),
            (13, "def3", "ghost"), (12, "def4", "special actor"),
            (11, "def5", "spider")]
    TBL_AMOUNT, TBL_RATE = 0xF296, 0xF2A5
    TBL_SCREEN_KIND = 0x6753        # f6: room -> which special-actor kind
    TBL_TOUGHNESS = 0x6433          # f6: kind -> seed written to sactor_damage

    # $EF is not a budget but a marker: LoadAreaHeader turns it into $22 when
    # the cross is held and $FF when it is not. Only areas carrying it respond
    # to the cross at all.
    CROSS_MARKER = 0xEF

    def expand_def(self, byte):
        return (self.byte("f7", self.TBL_AMOUNT + (byte >> 4)),
                self.byte("f7", self.TBL_RATE + (byte & 0x0F)))

    def spawns(self, kind):
        """The room's six budgets, decoded, plus the special actor's kind."""
        addr = self.area(kind)["addr"]
        out = []
        for off, name, who in self.DEFS:
            raw = self.byte("f7", addr + off)
            amount, rate = self.expand_def(raw)
            out.append({"offset": off, "slot": name, "spawns": who, "raw": raw,
                        "amount": amount, "rate": rate,
                        "cross_marker": raw == self.CROSS_MARKER})
        return {"budgets": out, "special": self.screen_kind(kind)}

    def set_spawn(self, kind, slot, value):
        for off, name, _ in self.DEFS:
            if name == slot:
                return self.poke("f7", self.area(kind)["addr"] + off, value & 0xFF)
        raise EditError("%r is not one of %s"
                        % (slot, ", ".join(n for _, n, _ in self.DEFS)))

    def screen_kind(self, kind):
        """Which creature the special-actor slot places.

        A positive entry pins one kind. A negative one is a mask: the kind is
        Random AND (entry & 7), so the room draws from a range.
        """
        v = self.byte("f6", self.TBL_SCREEN_KIND + kind)
        if v & 0x80:
            return {"raw": v, "fixed": None, "mask": v & 0x07,
                    "range": [k for k in range(8) if k & (v & 0x07) == k]}
        # kinds 10 and 11 seed sactor_damage with $00, which the per-frame walk
        # reads as an empty slot -- so an actor of either kind can never appear.
        return {"raw": v, "fixed": v, "mask": None,
                "dead": self.byte("f6", self.TBL_TOUGHNESS + v) == 0
                        if v < 16 else False}

    def set_screen_kind(self, kind, value):
        self.poke("f6", self.TBL_SCREEN_KIND + kind, value & 0xFF)

    # tbl_SactorToughness is 13 bytes, $6433-$643F. dat_6440 -- the head
    # graphics -- begins immediately after, so an index past 12 reads (and would
    # write) artwork. PickSactorKind cannot produce one either: its fixed
    # entries top out at $0C and its random masks are AND #$07.
    TOUGHNESS_N = 13
    WEAPONS = [("axe", 1), ("blaster", 2), ("mega blaster", 3)]

    def toughness(self):
        """Every special-actor kind, its seed, and what that costs to kill.

        Death is an 8-bit overflow of sactor_damage, so a seed S takes 256 - S
        points, and a weapon delivering L per hit needs ceil(points / L).
        """
        out = []
        placed = self.kind_users()
        for k in range(self.TOUGHNESS_N):
            seed = self.byte("f6", self.TBL_TOUGHNESS + k)
            pts = (256 - seed) & 0xFF or 256
            hits = {n: -(-pts // lvl) for n, lvl in self.WEAPONS}
            out.append({"kind": k, "seed": seed, "points": pts, "hits": hits,
                        # a zero seed reads as an empty slot on the next frame,
                        # so the actor is placed and immediately ignored
                        "inert": seed == 0, "rooms": placed.get(k, [])})
        return out

    def set_toughness(self, kind, seed):
        if not 0 <= kind < self.TOUGHNESS_N:
            raise EditError("kind %d is outside tbl_SactorToughness (0-%d); "
                            "writing past it would corrupt the head graphics at "
                            "f6:$6440" % (kind, self.TOUGHNESS_N - 1))
        self.poke("f6", self.TBL_TOUGHNESS + kind, seed & 0xFF)

    # Damage and stun constants, each the immediate operand of one instruction.
    # `op` is the opcode that must sit immediately before it -- $A9 LDA#, $69
    # ADC# -- so a rule can never write into code that has moved underneath it.
    # There is deliberately no entry for blood purity: the engine has no
    # "drain N" argument, it just calls the drain repeatedly, so purity costs
    # are a count of JSRs rather than a number anything could edit.
    RULES = [
        ("sactor_contact", "f6", 0x6718, 0xA9, 0x10,
         "Special actor contact", "Health lost touching a special actor. The "
         "largest contact hit in the game -- four times the worst an ordinary "
         "enemy does, and what makes the caves punishing."),
        ("tough_contact_base", "f6", 0x5FE2, 0x69, 0x02,
         "Tough actor contact base", "Health lost touching a tough actor is "
         "boss_flags * 2 + this, so it scales with progress: 2, 4, 6, 8 as "
         "bosses fall."),
        ("tough_stun", "f6", 0x5FED, 0xA9, 0x14,
         "Tough actor stun", "Frames the player is locked out after a tough "
         "actor's touch."),
        ("sactor_stun", "f6", 0x671D, 0xA9, 0x1E,
         "Special actor stun", "Frames locked out after a special actor's "
         "touch, while alive."),
        ("sactor_stun_dying", "f6", 0x6723, 0xA9, 0x06,
         "Special actor stun, dying", "The same, once death_state is set."),
    ]

    def rules(self):
        out = []
        for name, space, addr, op, default, label, note in self.RULES:
            out.append({"name": name, "at": "%s:$%04X" % (space, addr),
                        "value": self.byte(space, addr), "default": default,
                        "label": label, "note": note,
                        "anchored": self.byte(space, addr - 1) == op})
        return out

    def set_rule(self, name, value):
        for n, space, addr, op, _, _, _ in self.RULES:
            if n != name:
                continue
            if self.byte(space, addr - 1) != op:
                raise EditError("%s no longer sits behind the expected opcode "
                                "at %s:$%04X -- refusing to write into moved code"
                                % (name, space, addr))
            return self.poke(space, addr, value & 0xFF)
        raise EditError("no such rule: %r" % name)

    # Header +$0F loads throw_enable ($1FCC). It is not a flag but a rate mask:
    # f6:$6325 skips the throw when the byte is zero, and otherwise throws only
    # when `throw_enable AND throw_rate_mask` is zero. So every set bit halves
    # the rate -- $3F is one throw in 64, $01 is one in two.
    THROW = 0x0F

    def throwing(self, kind):
        raw = self.byte("f7", self.area(kind)["addr"] + self.THROW)
        return {"raw": raw, "enabled": raw != 0,
                "one_in": (1 << bin(raw).count("1")) if raw else None}

    def set_throwing(self, kind, value):
        self.poke("f7", self.area(kind)["addr"] + self.THROW, value & 0xFF)

    # Every instruction in the cartridge that names one inventory slot,
    # derived from the listings that rebuild byte-identically. Absolute
    # entries carry the slot in a two-byte operand; the four "sel" entries
    # compare sel_item against an id, so their operand is one byte.
    #
    # Indexed accesses are deliberately absent: `INC inventory,X` in
    # CollectItem names the base of the array, not a slot, and offering it
    # as a per-item gate would be a lie.
    ITEM_REFS = [
        ("b0", 0xA40C, "abs", 0xAD, "LDA", "Grampa's message chain: $17 without, $18/$19 at random with"),
        ("f6", 0x4EB3, "abs", 0xAD, "LDA", "the undead ending: holding this makes you a standing figure, not the bat"),
        ("f6", 0x5D02, "abs", 0xAD, "LDA", "three times in four an actor picks a random destination instead of homing"),
        ("f6", 0x5FB1, "abs", 0xAD, "LDA", "halves contact blood loss -- skips the second drain call"),
        ("f7", 0xD404, "abs", 0xAD, "LDA", "halves every source of health damage (DamageHealth)"),
        ("f7", 0xF067, "abs", 0xAE, "LDX", "spawn throttle: turns an area's $EF marker into $22 instead of $FF"),
        ("f7", 0xF1FD, "abs", 0xAD, "LDA", "a further per-area spawn limit"),
        ("b0", 0xA432, "abs", 0xAD, "LDA", "Grampa's message chain"),
        ("b0", 0xA446, "abs", 0xAD, "LDA", "Grampa's message chain"),
        ("b5", 0xB6E0, "abs", 0xAD, "LDA", "the boss status line"),
        ("f6", 0x6012, "abs", 0xAD, "LDA", "enters the purity ladder four calls early: a thrown hit costs 9, not 5"),
        ("b0", 0xA3E3, "abs", 0xAD, "LDA", "Grampa's message chain: the first test, so the heart wins his advice"),
        ("f7", 0xD41F, "abs", 0xAD, "LDA", "blood purity immunity -- the drain returns before touching it"),
        ("f7", 0xF239, "abs", 0xAD, "LDA", "the plasmic pumpkin's own spawn check"),
        ("f6", 0x509F, "abs", 0x8D, "STA", "potion use"),
        ("f6", 0x5230, "abs", 0xAD, "LDA", "auto-use on pickup"),
        ("f6", 0x5246, "abs", 0x8D, "STA", "potion use"),
        ("b5", 0xB6FD, "abs", 0xAD, "LDA", "the boss status line"),
        ("f6", 0x5255, "abs", 0xAD, "LDA", "auto-use: observed restoring hp_cur to hp_max"),
        ("f6", 0x5262, "abs", 0x8D, "STA", "pickup"),
        ("b0", 0xA458, "abs", 0xAD, "LDA", "Grampa's message chain"),
        ("f7", 0xF022, "abs", 0xAD, "LDA", "clears area_is_dark outright, lighting every dark room"),
        ("b0", 0xA3F8, "abs", 0xAD, "LDA", "Grampa's message chain"),
        ("b0", 0xA414, "abs", 0xAD, "LDA", "Grampa's message chain"),
        ("b0", 0xA435, "abs", 0x0D, "ORA", "Grampa's message chain"),
        ("f6", 0x5FAA, "sel", 0xC9, "CMP", "immune to contact blood loss while selected"),
        ("f6", 0x56E5, "sel", 0xC9, "CMP", "walks terrain $85 while selected"),
        ("f7", 0xD0C8, "sel", 0xC9, "CMP", "water walk while selected"),
        ("f6", 0x575F, "sel", 0xC9, "CMP", "wins the game on terrain $EF while selected"),
    ]

    # Fire-rate by weapon level, f6:$50ED, four bytes. Lower is faster, so
    # the weapon progression is partly a fire-rate upgrade. sub_50C4 reads
    # it into weapon_cooldown ($88) whenever weapon_level changes.
    WEAPON_DELAY = 0x50ED
    WEAPON_NAMES = ["knife", "axe", "blaster", "mega blaster"]

    INVENTORY = 0x1F3D

    def item_refs(self):
        """Every per-item reference, with the slot it currently names."""
        out = []
        for space, addr, kind, op, mn, note in self.ITEM_REFS:
            anchored = self.byte(space, addr - 1) == op
            if kind == "abs":
                v = self.byte(space, addr) | (self.byte(space, addr + 1) << 8)
                item = v - self.INVENTORY
            else:
                item = self.byte(space, addr)
            out.append({"at": "%s:$%04X" % (space, addr - 1), "space": space,
                        "addr": addr, "kind": kind, "mn": mn, "note": note,
                        "item": item, "anchored": anchored,
                        "writes": mn in ("STA", "STX", "STY", "INC", "DEC")})
        return out

    def set_item_ref(self, at, item):
        """Point one reference at a different inventory slot."""
        for space, addr, kind, op, mn, _ in self.ITEM_REFS:
            if "%s:$%04X" % (space, addr - 1) != at:
                continue
            if not 1 <= item <= 15:
                raise EditError("item id must be 1-15; the inventory has no slot %d" % item)
            if self.byte(space, addr - 1) != op:
                raise EditError("the opcode at %s is no longer $%02X -- refusing to "
                                "write into moved code" % (at, op))
            if kind == "abs":
                slot = self.INVENTORY + item
                self.poke(space, addr, bytes([slot & 0xFF, slot >> 8]))
            else:
                self.poke(space, addr, item)
            return
        raise EditError("no reference at %s" % at)

    def weapon_delays(self):
        return [{"level": i, "name": n,
                 "delay": self.byte("f6", self.WEAPON_DELAY + i)}
                for i, n in enumerate(self.WEAPON_NAMES)]

    def set_weapon_delay(self, level, delay):
        if not 0 <= level < len(self.WEAPON_NAMES):
            raise EditError("weapon level must be 0-%d; the table is four bytes "
                            "and $50F1 is the next instruction"
                            % (len(self.WEAPON_NAMES) - 1))
        self.poke("f6", self.WEAPON_DELAY + level, delay & 0xFF)

    # The health ceiling: what moves it, what bounds it, and what it unlocks.
    # These five constants are one mechanic. hp_max starts at $27; the diamond
    # is the only thing that raises it and the ghost the only thing that lowers
    # it, and revival compares against a threshold -- so the diamond's gain and
    # the threshold together decide how many diamonds a second life costs.
    HEALTH = [
        ("hp_start", "f6", 0x4AE4, 0xA9, 0x27, "Starting health",
         "Written to both hp_cur and hp_max at reset."),
        ("diamond_gain", "f6", 0x5213, 0x69, 0x08, "Diamond raises hp_max by",
         "CollectItem adds this to hp_max and refills hp_cur. Nothing ever "
         "reads the diamond's inventory counter -- the effect happens at "
         "pickup, so the counter exists only to draw the icon."),
        ("ghost_drain", "f6", 0x5891, 0xE9, 0x08, "Ghost touch lowers hp_max by",
         "CheckGhostTouch is the only thing in the game that reduces hp_max, "
         "which is why a long crypt fight quietly undoes diamonds."),
        ("hp_max_floor", "f6", 0x5881, 0xC9, 0x11, "Floor on hp_max",
         "The ghost drain does nothing once hp_max is below this, so the "
         "ceiling can never be drained to zero."),
        ("ghost_cooldown", "f6", 0x587B, 0xA9, 0x28, "Frames between ghost drains",
         "A 40-frame lockout before another drain can land."),
        ("revive_at", "f6", 0x4EC2, 0xC9, 0x30, "Revival needs hp_max of",
         "Running out of health is survivable only at or above this. Blood "
         "loss never is."),
    ]

    def health(self):
        out = []
        for name, space, addr, op, default, label, note in self.HEALTH:
            out.append({"name": name, "at": "%s:$%04X" % (space, addr - 1),
                        "value": self.byte(space, addr), "default": default,
                        "label": label, "note": note,
                        "anchored": self.byte(space, addr - 1) == op})
        d = {x["name"]: x["value"] for x in out}
        # how many diamonds a second life costs, given the current numbers
        gain, start, need = d["diamond_gain"], d["hp_start"], d["revive_at"]
        if start >= need:
            cost = 0
        elif gain <= 0:
            cost = None                      # unreachable: nothing raises hp_max
        else:
            cost = -(-(need - start) // gain)
        return {"values": out, "diamonds_to_revive": cost}

    def set_health(self, name, value):
        for n, space, addr, op, _, _, _ in self.HEALTH:
            if n != name:
                continue
            if self.byte(space, addr - 1) != op:
                raise EditError("the opcode at %s:$%04X is no longer $%02X -- "
                                "refusing to write into moved code"
                                % (space, addr - 1, op))
            return self.poke(space, addr, value & 0xFF)
        raise EditError("no such health constant: %r" % name)

    # ---------------------------------------------------------------- bosses
    # b5:$B013 reads a 32-byte setup record through a pointer table; slot 0 is
    # null and the three bosses are numbered 1-3. Contact damage is not in the
    # record but in a table indexed by mode_flag, whose base overlaps an RTS --
    # entry 0 is that $60 byte and is never read, because mode_flag is 1-3
    # throughout a fight.
    BOSS_PTRS = 0xB19F
    BOSS_CONTACT = 0xBBFD
    BOSS_NAMES = {1: "Skull", 2: "Ram", 3: "Dr Evil"}
    BOSS_FIELDS = [
        ("health", 6, "Health", "One point comes off per hit whatever the "
         "weapon, so this is the hit count -- and the knife is refused outright."),
        ("palette", 0, "Palette set", "Selects a 40-byte block via dat5_B207."),
        ("fire_dir", 7, "Fire direction", ""),
        ("start_long", 8, "Player start, long", ""),
        ("start_cross", 9, "Player start, cross", ""),
        ("stage", 14, "Stage counter start",
         "The escalation index. $00 for all three as shipped, so every fight "
         "begins at its calmest."),
    ]

    # The end-of-fight reward, applied by BossSequenceReward (b5:$B637).
    BOSS_WIN = [
        ("win_hp_max", "b5", 0xB63B, 0x69, 0x10, "Victory raises hp_max by",
         "The only source of hp_max besides the diamond, and twice as "
         "generous. Beating all three is worth $30 on its own."),
        ("win_purity", "b5", 0xB641, 0xA9, 0x64, "Victory sets blood purity to",
         "A full refill at 100, so a won fight undoes every drain taken "
         "getting there."),
    ]

    def boss_addr(self, n):
        lo = self.byte("b5", self.BOSS_PTRS + n * 2)
        hi = self.byte("b5", self.BOSS_PTRS + n * 2 + 1)
        ptr = lo | (hi << 8)
        if ptr < 0x8000:
            raise EditError("boss %d has a null setup record" % n)
        return ptr

    def bosses(self):
        out = []
        for n in sorted(self.BOSS_NAMES):
            addr = self.boss_addr(n)
            fields = [{"key": k, "label": lab, "note": note,
                       "value": self.byte("b5", addr + off)}
                      for k, off, lab, note in self.BOSS_FIELDS]
            out.append({"n": n, "name": self.BOSS_NAMES[n],
                        "at": "b5:$%04X" % addr, "fields": fields,
                        "contact": self.byte("b5", self.BOSS_CONTACT + n)})
        return {"bosses": out, "win": [
            {"name": nm, "at": "%s:$%04X" % (sp, ad - 1),
             "value": self.byte(sp, ad), "default": dv, "label": lab,
             "note": nt, "anchored": self.byte(sp, ad - 1) == op}
            for nm, sp, ad, op, dv, lab, nt in self.BOSS_WIN]}

    def set_boss(self, n, field, value):
        if n not in self.BOSS_NAMES:
            raise EditError("boss must be 1, 2 or 3; slot 0 is a null pointer")
        if field == "contact":
            return self.poke("b5", self.BOSS_CONTACT + n, value & 0xFF)
        for k, off, _, _ in self.BOSS_FIELDS:
            if k == field:
                return self.poke("b5", self.boss_addr(n) + off, value & 0xFF)
        raise EditError("%r is not an editable boss field" % field)

    def set_boss_win(self, name, value):
        for nm, sp, ad, op, _, _, _ in self.BOSS_WIN:
            if nm != name:
                continue
            if self.byte(sp, ad - 1) != op:
                raise EditError("the opcode at %s:$%04X is no longer $%02X -- "
                                "refusing to write into moved code" % (sp, ad - 1, op))
            return self.poke(sp, ad, value & 0xFF)
        raise EditError("no such victory constant: %r" % name)

    # ------------------------------------------------------- terrain properties
    # The grid stores a character number; its behaviour comes from the area's
    # property table indexed by (cell >> 1) & $7F, so two adjacent characters
    # share one property. Six tables cover all 76 rooms.
    #
    # CheckTerrainUnderPlayer (f6:$55E3) reads a byte and branches three ways:
    #   $00        nothing -- open ground
    #   bit 7 set  a scripted square, latched into pending_terrain
    #   otherwise  bits 0-1 are the collision class: 3 blocks everywhere,
    #              1 and 2 block only their half of the cell diagonal
    TBL_PROP_LO, TBL_PROP_HI = 0xFEC7, 0xFED0
    PROP_LEN = 0x80
    # cell_half is 1 when 2*x + y within the cell reaches $10 and 2 below it,
    # and a class blocks when it equals cell_half -- so the two halves are the
    # two sides of a diagonal through the cell.
    COLLISION = {0: "open", 1: "blocks the lower right half",
                 2: "blocks the upper left half", 3: "solid"}
    # Bit 2 is never tested by CheckTerrainUnderPlayer -- the collision test is
    # only AND #$03 -- so $05/$06/$07 block exactly as $01/$02/$03 do. It marks
    # water for the authors rather than telling the engine anything, and the
    # values sit almost entirely in the pond of room $01.
    WATER_BIT = 0x04
    EVENTS = {
        0x81: "door to $2B", 0x82: "door to $14, needs a weapon",
        0x83: "door to $15, forces a message", 0x84: "door to $16, needs a weapon",
        0x85: "door to $1E, needs the crypt key SELECTED",
        0x86: "door to $1C, needs the Ram beaten, a weapon, nothing selected",
        0x8C: "door taking the west destination",
        0x8E: "door taking the south table", 0x8F: "door taking the north table",
        0x90: "paired door: $16 and $36 lead to each other",
        0xA0: "the healing well", 0xA1: "hurting ground", 0xEF: "the win square",
        0xF1: "boss door: Skull", 0xF2: "boss door: Ram", 0xF3: "boss door: Dr Evil",
    }

    # The same events, broken into parts a layer can draw. Three of them do not
    # name a destination at all -- they defer to the room's own header, so where
    # they lead depends on which room and, for the north and south tables, which
    # segment the tile sits in.
    EVENT_INFO = {
        0x81: {"kind": "door", "dest": 0x2B},
        0x82: {"kind": "door", "dest": 0x14, "needs": "a weapon"},
        0x83: {"kind": "door", "dest": 0x15, "needs": "shows a message first"},
        0x84: {"kind": "door", "dest": 0x16, "needs": "a weapon"},
        0x85: {"kind": "door", "dest": 0x1E,
               "needs": "the crypt key selected"},
        0x86: {"kind": "door", "dest": 0x1C,
               "needs": "the Ram beaten, a weapon, nothing selected"},
        0x8C: {"kind": "door", "via": "west"},
        0x8E: {"kind": "door", "via": "south"},
        0x8F: {"kind": "door", "via": "north"},
        0x90: {"kind": "door", "pair": [0x16, 0x36],
               "needs": "leads back the way it came"},
        0xA0: {"kind": "well"},
        0xA1: {"kind": "hazard"},
        0xEF: {"kind": "win", "needs": "the plasmic pumpkin selected"},
        0xF1: {"kind": "boss", "boss": "Skull"},
        0xF2: {"kind": "boss", "boss": "Ram"},
        0xF3: {"kind": "boss", "boss": "Dr Evil"},
    }

    def event_info(self):
        """The event table with its label, for the room-view exit layer."""
        out = {}
        for v, d in self.EVENT_INFO.items():
            e = dict(d)
            e["label"] = self.EVENTS.get(v, "event $%02X" % v)
            out["%d" % v] = e
        return out

    def prop_addr(self, page):
        return (self.byte("f7", self.TBL_PROP_LO + page)
                | (self.byte("f7", self.TBL_PROP_HI + page) << 8))

    def prop_tables(self):
        """Each distinct property table, and which rooms use it."""
        out = {}
        for k in self.rooms():
            out.setdefault(self.prop_addr(self.area(k)["page"]), []).append(k)
        return out

    def properties(self, kind):
        """The room's property table, one entry per (cell >> 1), with which
        characters in this room actually reach each entry."""
        page = self.area(kind)["page"]
        ptr = self.prop_addr(page)
        if not (0xC000 <= ptr < 0xFFF0):
            raise EditError("area page %d has no property table" % page)
        grid = self.grid(kind) or []
        used = {}
        for cell in grid:
            if cell:
                used.setdefault((cell >> 1) & 0x7F, set()).add(cell)
        rows = []
        for i in range(self.PROP_LEN):
            v = self.byte("f7", ptr + i)
            rows.append({
                "index": i, "value": v,
                "scripted": bool(v & 0x80),
                "event": self.EVENTS.get(v) if v & 0x80 else None,
                "collision": None if v & 0x80 else self.COLLISION.get(v & 3),
                "water": bool(v & self.WATER_BIT) and not (v & 0x80),
                "chars": sorted(used.get(i, ())),
            })
        return {"addr": ptr, "page": page, "rows": rows,
                "rooms": len(self.prop_tables().get(ptr, []))}

    def set_property(self, kind, index, value):
        if not 0 <= index < self.PROP_LEN:
            raise EditError("property index must be 0-%d" % (self.PROP_LEN - 1))
        ptr = self.prop_addr(self.area(kind)["page"])
        if not (0xC000 <= ptr < 0xFFF0):
            raise EditError("this area has no property table")
        self.poke("f7", ptr + index, value & 0xFF)

    # ------------------------------------------------------------------ doors
    # Each scripted door carries its destination as an immediate right before
    # the jump that performs the move. The gates are separate tests -- the
    # crypt key one is a sel_item compare and already appears among the item
    # references, so only the boss_flags masks are listed here.
    DOORS = [
        (0x81, "f6", 0x5692, 0x2B, "$11 -> $2B", ""),
        (0x82, "f6", 0x56B5, 0x14, "$01 -> $14", "needs a weapon"),
        (0x83, "f6", 0x56C7, 0x15, "$08 -> $15", "forces a message"),
        (0x84, "f6", 0x56DA, 0x16, "$13 -> $16", "needs weapon_level > 0"),
        (0x85, "f6", 0x56FF, 0x1E, "$17 -> $1E", "needs the crypt key SELECTED"),
        (0x86, "f6", 0x5730, 0x1C, "$40 -> $1C", "needs the Ram beaten, a weapon, nothing selected"),
        (0x90, "f6", 0x5745, 0x36, "$16 <-> $36, one way", "paired door"),
        (0x90, "f6", 0x574B, 0x16, "$16 <-> $36, the other", "paired door"),
    ]
    DOOR_GATES = [
        ("door85_boss", "f6", 0x56EC, 0x29, 0x01, "$85 fallback gate",
         "Without the crypt key selected this bit decides whether you get the "
         "refusal glyph."),
        ("door86_boss", "f6", 0x5711, 0x29, 0x01, "$86 boss gate",
         "boss_flags bit 0 -- the Ram."),
    ]

    def doors(self):
        out = []
        for code, space, addr, default, where, note in self.DOORS:
            out.append({"code": code, "at": "%s:$%04X" % (space, addr - 1),
                        "addr": addr, "space": space, "where": where,
                        "note": note, "default": default,
                        "dest": self.byte(space, addr),
                        "anchored": self.byte(space, addr - 1) == 0xA9})
        gates = [{"name": n, "at": "%s:$%04X" % (sp, ad - 1), "label": lab,
                  "note": nt, "value": self.byte(sp, ad), "default": dv,
                  "anchored": self.byte(sp, ad - 1) == op}
                 for n, sp, ad, op, dv, lab, nt in self.DOOR_GATES]
        return {"doors": out, "gates": gates}

    def set_door(self, at, dest):
        for code, space, addr, _, _, _ in self.DOORS:
            if "%s:$%04X" % (space, addr - 1) != at:
                continue
            if self.byte(space, addr - 1) != 0xA9:
                raise EditError("the opcode at %s is no longer $A9 LDA# -- "
                                "refusing to write into moved code" % at)
            if dest not in self.rooms():
                raise EditError("room $%02X is not a real room" % dest)
            return self.poke(space, addr, dest & 0xFF)
        raise EditError("no door at %s" % at)

    def set_door_gate(self, name, value):
        for n, sp, ad, op, _, _, _ in self.DOOR_GATES:
            if n == name:
                if self.byte(sp, ad - 1) != op:
                    raise EditError("the opcode before %s:$%04X moved" % (sp, ad))
                return self.poke(sp, ad, value & 0xFF)
        raise EditError("no such door gate: %r" % name)

    # -------------------------------------------------------------- new game
    START = [
        ("start_purity", "f6", 0x4AE0, 0xA9, 0x64, "Starting blood purity",
         "Out of 100. Reaching zero ends the run outright."),
        ("start_health", "f6", 0x4AE4, 0xA9, 0x27, "Starting health",
         "Written to hp_cur and hp_max alike, so it is also the ceiling you "
         "begin with."),
    ]

    def start_state(self):
        return [{"name": n, "at": "%s:$%04X" % (sp, ad - 1), "label": lab,
                 "note": nt, "value": self.byte(sp, ad), "default": dv,
                 "anchored": self.byte(sp, ad - 1) == op}
                for n, sp, ad, op, dv, lab, nt in self.START]

    def set_start(self, name, value):
        for n, sp, ad, op, _, _, _ in self.START:
            if n == name:
                if self.byte(sp, ad - 1) != op:
                    raise EditError("the opcode before %s:$%04X moved" % (sp, ad))
                return self.poke(sp, ad, value & 0xFF)
        raise EditError("no such starting value: %r" % name)

    # ------------------------------------------------------------------- text
    # Two framings, both scanned the same way tools/text.py does:
    #
    #   A  "$FF <p1> <p2> '@' text '#'"          -- the dialogue pool
    #   B  "<$FE|$FF> <p1> <p2> text"            -- credits and cutscenes, with
    #      no introducer and no terminator; the text simply runs to the next
    #      $FE or $FF.
    #
    # Records are packed end to end either way, so replacement text may be
    # shorter but never longer. A short one is padded with spaces rather than
    # moving everything after it.
    TEXT_SPACES = ["b0", "f6"]
    PRINTABLE = set(range(0x20, 0x7F))

    def _bank_bytes(self, space):
        b = self.bank_of(space)
        return bytes(self.rom[b * BANK_SIZE:(b + 1) * BANK_SIZE])

    def texts(self):
        out = []
        for space in self.TEXT_SPACES:
            base = self.base_of(space)
            data = self._bank_bytes(space)
            seen = set()
            # framing A
            i = 0
            while i < len(data) - 4:
                if data[i] == 0xFF and data[i + 3] == 0x40:
                    e = data.find(b"#", i + 4)
                    if 0 < e - (i + 4) < 1024:
                        out.append({"space": space, "addr": base + i + 4,
                                    "at": "%s:$%04X" % (space, base + i),
                                    "framing": "A", "p1": data[i + 1],
                                    "p2": data[i + 2], "p2_at": base + i + 2,
                                    "capacity": e - (i + 4),
                                    "text": data[i + 4:e].decode("latin-1")})
                        seen.update(range(i, e + 1))
                        i = e + 1
                        continue
                i += 1
            # framing B, skipping anything framing A already claimed
            i = 0
            while i < len(data) - 4:
                if data[i] in (0xFE, 0xFF) and i not in seen:
                    j = k = i + 3
                    while k < len(data) and data[k] in self.PRINTABLE:
                        k += 1
                    if k - j >= 10 and k < len(data) and data[k] in (0xFE, 0xFF):
                        if not (set(range(i, k)) & seen):
                            out.append({"space": space, "addr": base + j,
                                        "at": "%s:$%04X" % (space, base + i),
                                        "framing": "B", "p1": data[i + 1],
                                        "p2": data[i + 2], "p2_at": base + i + 2,
                                        "capacity": k - j,
                                        "term": data[k], "term_at": base + k,
                                        "shimmer": data[k] == 0xFE,
                                        "text": data[j:k].decode("latin-1")})
                            seen.update(range(i, k))
                        i = k
                        continue
                i += 1
        out.sort(key=lambda r: (r["space"], r["addr"]))
        return out

    def set_text(self, space, addr, text):
        for r in self.texts():
            if r["addr"] == addr and r["space"] == space:
                t = text.upper().encode("ascii", "replace")
                bad = [c for c in t if c not in self.PRINTABLE]
                if bad:
                    raise EditError("only printable ASCII; the control codes are "
                                    "| newline, & new page, ^ apostrophe, * glyph")
                if len(t) > r["capacity"]:
                    raise EditError("%d characters will not fit: this record holds "
                                    "%d, and records are packed end to end so it "
                                    "cannot grow" % (len(t), r["capacity"]))
                self.poke(space, addr, t + b" " * (r["capacity"] - len(t)))
                return
        raise EditError("no text record at %s:$%04X" % (space, addr))

    # p2 is how long the banner holds. sub_687E copies it to ram_1E7A and
    # f6:$40CF counts that down once every 32 frames, so a value is a little
    # over half a second each. Zero means the message is replaced as soon as
    # anything else asks for the banner.
    def set_text_param(self, space, addr, p2):
        if not 0 <= int(p2) <= 0xFF:
            raise EditError("the hold is one byte, $00-$FF")
        for r in self.texts():
            if r["addr"] == addr and r["space"] == space:
                return self.poke(space, r["p2_at"], int(p2))
        raise EditError("no text record at %s:$%04X" % (space, addr))

    # ------------------------------------------- pickups that never shimmer
    # A record's terminator decides whether the banner pulses: $FE puts $FF in
    # the mask the display interrupt ANDs the frame counter with, $FF leaves it
    # at zero. Auditing every message a pickup can raise, four end $FF while
    # everything around them ends $FE -- the cross, and the three weapon
    # upgrades above the knife. The knife's own four messages shimmer, as do
    # both potions, the crypt key, necklace, heart, lantern and all four diamond
    # variants, so these four are the odd ones out rather than a house style.
    PICKUP_DULL = [
        ("cross", 0x7236, "$33"),
        ("axe", 0x717E, "$2F"),
        ("blaster", 0x71BB, "$30"),
        ("mega blaster", 0x71F9, "$31"),
    ]

    def pickup_shimmer(self):
        out = []
        for name, at, idx in self.PICKUP_DULL:
            a = self.at("f6", at)
            v = self.byte("f6", a)
            out.append({"name": name, "record": idx, "at": "f6:$%04X" % a,
                        "value": "$%02X" % v, "on": v == 0xFE,
                        "ok": v in (0xFE, 0xFF)})
        done = [x["on"] for x in out]
        return {"entries": out, "on": all(done),
                "state": "on" if all(done) else
                         "off" if not any(done) else "partial",
                "bytes": len(out)}

    def set_pickup_shimmer(self, on):
        for name, at, idx in self.PICKUP_DULL:
            a = self.at("f6", at)
            v = self.byte("f6", a)
            if v not in (0xFE, 0xFF):
                raise EditError("f6:$%04X holds $%02X, which is not a record "
                                "marker -- refusing to overwrite it" % (a, v))
            self.poke("f6", a, 0xFE if on else 0xFF)

    # The byte that ends a framing-B record decides whether the banner shimmers.
    # sub_687E scans to the first byte with bit 7 set and, if it is $FE, puts
    # $FF in ram_1E7B; the display interrupt then runs
    #     LDA ram_0044 / AND ram_1E7B / STA P0C2      (f6:$4121)
    # so the frame counter walks the text colour a step per frame. $FF leaves
    # the mask at zero and the words sit on colour 0. Every stock item pickup
    # ends $FE; the title, the cross, the weapons and the stuck door do not.
    #
    # Records are packed end to end, so this byte is also the *next* record's
    # marker -- but nothing reads that. The pointer table aims at each record's
    # p1, and the scanner accepts either value, so flipping it changes only the
    # shimmer of the record it terminates.
    def set_text_shimmer(self, space, addr, shimmer):
        for r in self.texts():
            if r["addr"] == addr and r["space"] == space:
                if r["framing"] != "B":
                    raise EditError("framing A records end with '#' and are not "
                                    "drawn by the banner routine, so there is no "
                                    "shimmer to set")
                # That byte is shared with whatever follows. Nothing reads it as
                # a framing-B marker, but framing A is introduced by $FF and is
                # recognised by it, so a record that opens one must keep it.
                k = r["term_at"] - self.base_of(space)
                data = self._bank_bytes(space)
                if (not shimmer) or not (k + 3 < len(data) and data[k] == 0xFF
                                         and data[k + 3] == 0x40):
                    self.poke(space, r["term_at"], 0xFE if shimmer else 0xFF)
                    return
                raise EditError(
                    "%s:$%04X ends this record but also opens the framing-A "
                    "record after it, which is recognised by its $FF -- turning "
                    "the shimmer on here would hide that record"
                    % (space, r["term_at"]))
        raise EditError("no text record at %s:$%04X" % (space, addr))

    # ------------------------------------------------- boss hitbox and portrait
    # The setup walk at b5:$B040 copies the record's first six bytes into RAM,
    # and four of them are the hitbox: record +2/+3 are the long-axis edges as
    # offsets from boss_pos, +4/+5 the cross-axis edges. BossVsProjectiles
    # (b5:$B4D7) tests a shot against exactly those, so they are the weak spot.
    #
    # Only Dr Evil's marks can be tied to the picture from the ROM alone: the
    # Skull's and the Ram's portraits are narrower than the screen, so the
    # window origin is not the blit column and the horizontal mapping is
    # observation rather than derivation (see the note on the bosses page).
    # Everything here is therefore reported and edited as the raw byte plus its
    # distance from stock -- a shift, not a screen coordinate.
    BOSS_BOX = [("long_lo", 2, "Long axis, near edge"),
                ("long_hi", 3, "Long axis, far edge"),
                ("cross_lo", 4, "Cross axis, near edge"),
                ("cross_hi", 5, "Cross axis, far edge")]
    BOSS_BOX_STOCK = {1: (0x3C, 0x44, 0x40, 0x50),
                      2: (0x50, 0x5A, 0x18, 0x24),
                      3: (0x52, 0x5C, 0x40, 0x50)}

    # Dr Evil rewrites the long edges every frame from one of two bases, so his
    # record's +2/+3 never survive the first update. These are what move him.
    EARS = [("left", "b5", 0xB3EE, 0xA9, 0x2E, "Left window base",
             "Taken when bit 7 of $45 is set."),
            ("right", "b5", 0xB3F6, 0xA9, 0x66, "Right window base",
             "Taken when it is clear."),
            ("width", "b5", 0xB3FC, 0x69, 0x0A, "Window width",
             "Added to whichever base is live to give the far edge."),
            ("shot_left", "b5", 0xBAF4, 0x69, 0x34, "Shot offset, left",
             "Where the projectile leaves the head. The shot always comes "
             "from the ear you can currently hit, so moving a window without "
             "moving this breaks the tell."),
            ("shot_right", "b5", 0xBAFC, 0x69, 0x66, "Shot offset, right", "")]

    def boss_box(self, n):
        addr = self.boss_addr(n)
        stock = self.BOSS_BOX_STOCK[n]
        out = []
        for i, (key, off, label) in enumerate(self.BOSS_BOX):
            v = self.byte("b5", addr + off)
            out.append({"key": key, "at": "b5:$%04X" % (addr + off),
                        "value": v, "stock": stock[i],
                        "shift": ((v - stock[i] + 128) & 0xFF) - 128,
                        "label": label})
        return {"n": n, "name": self.BOSS_NAMES[n], "fields": out,
                "live": n == 3,
                "size": {"long": (out[1]["value"] - out[0]["value"]) & 0xFF,
                         "cross": (out[3]["value"] - out[2]["value"]) & 0xFF}}

    def set_boss_box(self, n, key, value):
        addr = self.boss_addr(n)
        for k, off, _ in self.BOSS_BOX:
            if k == key:
                return self.poke("b5", addr + off, int(value) & 0xFF)
        raise EditError("no such hitbox edge: %r" % key)

    def shift_boss_box(self, n, axis, by):
        """Move both edges of one axis together, keeping the window's size."""
        pair = ("long_lo", "long_hi") if axis == "long" else ("cross_lo", "cross_hi")
        cur = {f["key"]: f["value"] for f in self.boss_box(n)["fields"]}
        for k in pair:
            self.set_boss_box(n, k, (cur[k] + int(by)) & 0xFF)

    def boss_ears(self):
        out = []
        for key, sp, ad, op, dv, label, note in self.EARS:
            a = self.at(sp, ad)
            v = self.byte(sp, a)
            out.append({"key": key, "at": "%s:$%04X" % (sp, a), "value": v,
                        "stock": dv, "shift": ((v - dv + 128) & 0xFF) - 128,
                        "label": label, "note": note,
                        "anchored": self.byte(sp, a - 1) == op})
        return out

    def set_boss_ear(self, key, value):
        for k, sp, ad, op, _, _, _ in self.EARS:
            if k != key:
                continue
            a = self.at(sp, ad)
            if self.byte(sp, a - 1) != op:
                raise EditError("the opcode before %s:$%04X moved" % (sp, a))
            return self.poke(sp, a, int(value) & 0xFF)
        raise EditError("no such value: %r" % key)

    # The portrait is blitted from the record's four (src lo, src hi, column,
    # row) groups at +16. Exactly one is populated per boss, and what it blits
    # is the boss itself: a width/height header then one character per cell.
    def boss_art(self, n):
        p = self.boss_addr(n)
        for g in range(4):
            lo, hi, col, row = [self.byte("b5", p + 16 + g * 4 + k)
                                for k in range(4)]
            if not hi:
                continue
            src = lo | (hi << 8)
            w, h = self.byte("b5", src), self.byte("b5", src + 1)
            cells = [self.byte("b5", src + 4 + i) for i in range(w * h)]
            return {"n": n, "name": self.BOSS_NAMES[n], "at": "b5:$%04X" % src,
                    "data": "b5:$%04X" % (src + 4), "w": w, "h": h,
                    "col": col, "row": row, "cells": cells}
        raise EditError("boss %d blits nothing" % n)

    # A fight does not load an area, so its colours come from their own table:
    # record byte +0 picks a 40-byte block through dat5_B207, laid out exactly
    # like an area's -- ten bands of four, the last three of each being the
    # palette. Byte +1 is the character set, and bank 5 is mapped throughout.
    ARENA_PAL = 0xB207

    def arena_palette(self, pal_set):
        """Ten bands of three RGB triples, the arena equivalent of
        palette_bands. Read through the ROM's own pointer so the European
        layout works unchanged."""
        from palette import ntsc7800
        a = self.at("b5", self.ARENA_PAL)
        ptr = (self.byte("b5", a + pal_set * 2)
               | (self.byte("b5", a + pal_set * 2 + 1) << 8))
        return [[ntsc7800(self.byte("b5", ptr + b * self.PAL_STRIDE + c))
                 for c in (1, 2, 3)] for b in range(self.PAL_BANDS)]

    def boss_art_view(self, n):
        """boss_art plus everything needed to draw it: the character set it is
        built from, and the palette the bands it covers are shown in.

        The portrait is pasted into the 100x10 character map at (col, row), so
        a cell's colours come from the map band it lands in, not from the
        portrait's own row -- a tall portrait is drawn in more than one palette.
        """
        a = self.boss_art(n)
        p = self.boss_addr(n)
        pal_set, charbase = self.byte("b5", p), self.byte("b5", p + 1)
        import rooms
        cs = rooms.charset(self, 5, charbase)
        flat = bytearray()
        for ch in range(len(cs)):
            for ln in range(rooms.CHAR_H):
                flat += bytes(cs[ch][ln])
        a.update({"pal_set": pal_set, "charbase": charbase,
                  "palette": self.arena_palette(pal_set),
                  "charset": bytes(flat), "chars": len(cs),
                  "cols": 100, "bands": self.PAL_BANDS,
                  "record": "b5:$%04X" % p})
        return a

    def set_boss_art(self, n, index, value):
        a = self.boss_art(n)
        if not 0 <= int(index) < a["w"] * a["h"]:
            raise EditError("cell must be 0-%d for this %dx%d portrait"
                            % (a["w"] * a["h"] - 1, a["w"], a["h"]))
        base = int(a["data"].split("$")[1], 16)
        self.poke("b5", base + int(index), int(value) & 0xFF)

    # ------------------------------------------------------------ blood purity
    # DrainBloodPurity takes exactly one point per call and has no argument, so
    # a larger loss is written as more JSRs in a row -- seven runs, seventeen
    # calls. That is what makes the cost editable after all: a call is three
    # bytes and so are three NOPs, so a point can be removed without moving
    # anything. Nothing here is timing-sensitive; these are damage sites.
    DRAIN = bytes([0x20, 0x39, 0xD0])          # JSR sub_D039
    NOP3 = bytes([0xEA, 0xEA, 0xEA])
    DRAIN_SITES = {
        ("f6", 0x5B69): (1, "the periodic bleed -- one point every fourth tick"),
        ("f6", 0x5FAD): (1, "enemy contact; skipped while the cross is selected"),
        ("f6", 0x5FB5): (1, "enemy contact, second point; skipped if you own "
                            "the cross"),
        ("f6", 0x5FE6): (2, "tough-actor contact"),
        ("f6", 0x6016): (9, "enemy projectile -- the nine-call ladder"),
        ("f6", 0x6728): (2, "special-actor contact"),
        ("b5", 0xBBE1): (1, "Dr. Evil contact"),
    }

    # The projectile ladder is the only one with a conditional entry point. The
    # necklace test picks which rung execution starts on: holding it enters at
    # the top and takes all nine, otherwise the branch skips four and takes
    # five. Two separate things are therefore editable -- how many rungs exist,
    # and where the branch lands -- plus whether the test happens at all.
    LADDER = ("f6", 0x6016)
    LADDER_GATE = 0x6011                       # LDA itm_necklace
    LADDER_GATE_STOCK = bytes([0xAD, 0x40, 0x1F])
    LADDER_GATE_OFF = bytes([0xA9, 0x00, 0xEA])   # LDA #$00 / NOP -- Z always set
    LADDER_BRANCH = 0x6015                     # the BEQ operand

    def _drain_slot(self, space, at):
        b = bytes(self.slice(space, at, 3))
        return "call" if b == self.DRAIN else "nop" if b == self.NOP3 else "?"

    def purity_drains(self):
        out = []
        for (sp, a0) in sorted(self.DRAIN_SITES):
            n, label = self.DRAIN_SITES[(sp, a0)]
            a = self.at(sp, a0)
            slots = [self._drain_slot(sp, a + 3 * i) for i in range(n)]
            out.append({"space": sp, "addr": a, "at": "%s:$%04X" % (sp, a),
                        "slots": n, "active": slots.count("call"),
                        "intact": "?" not in slots, "label": label,
                        "ladder": (sp, a0) == self.LADDER})
        return out

    def set_purity_drain(self, space, addr, n):
        for s in self.purity_drains():
            if s["space"] != space or s["addr"] != addr:
                continue
            if not s["intact"]:
                raise EditError("%s holds something other than calls and NOPs "
                                "-- refusing to overwrite it" % s["at"])
            if not 0 <= int(n) <= s["slots"]:
                raise EditError("this site has %d call%s, so the cost can be "
                                "0 to %d" % (s["slots"],
                                             "" if s["slots"] == 1 else "s",
                                             s["slots"]))
            for i in range(s["slots"]):
                self.poke(space, addr + 3 * i,
                          self.DRAIN if i < int(n) else self.NOP3)
            return
        raise EditError("no drain site at %s:$%04X" % (space, addr))

    def purity_necklace(self):
        a = self.at("f6", self.LADDER[1])
        gate, br = self.at("f6", self.LADDER_GATE), self.at("f6", self.LADDER_BRANCH)
        here = bytes(self.slice("f6", gate, 3))
        slots = [self._drain_slot("f6", a + 3 * i) for i in range(9)]
        op = self.byte("f6", br)
        skip = op // 3
        checks = here == self.LADDER_GATE_STOCK
        without = slots[skip:].count("call") if skip <= 9 else 0
        return {"at": "f6:$%04X" % a, "gate_at": "f6:$%04X" % gate,
                "branch_at": "f6:$%04X" % br, "operand": op, "skip": skip,
                "slots": slots, "rungs": slots.count("call"),
                "checks_necklace": checks,
                "gate": "on" if checks else
                        "off" if here == self.LADDER_GATE_OFF else "modified",
                "with": slots.count("call") if checks else without,
                "without": without,
                "aligned": op % 3 == 0 and skip <= 9 and "?" not in slots}

    def set_purity_necklace(self, checks=None, without=None):
        cur = self.purity_necklace()
        if not cur["aligned"]:
            raise EditError("the ladder at %s is not the stock shape any more "
                            "-- refusing to edit it" % cur["at"])
        if checks is not None:
            if cur["gate"] == "modified":
                raise EditError("%s is neither the necklace test nor the "
                                "repair" % cur["gate_at"])
            self.poke("f6", self.at("f6", self.LADDER_GATE),
                      self.LADDER_GATE_STOCK if checks else self.LADDER_GATE_OFF)
        if without is not None:
            want = int(without)
            slots = cur["slots"]
            for skip in range(10):
                if slots[skip:].count("call") == want:
                    return self.poke("f6", self.at("f6", self.LADDER_BRANCH),
                                     3 * skip)
            raise EditError("no entry point gives %d point%s: the ladder holds "
                            "%d call%s" % (want, "" if want == 1 else "s",
                                           cur["rungs"],
                                           "" if cur["rungs"] == 1 else "s"))

    # ----------------------------------------------------------- sound effects
    # Writing an effect id to sfx_request ($1AF8) is the whole interface. The
    # tick at b0:$A018 looks the id up in a pointer table, copies the stream
    # pointer to $CD/$CE and clears the request; a request always replaces
    # whatever is playing. Two separate things are editable: which id each event
    # asks for, and what each id sounds like.
    SFX_REQ = 0x1AF8
    SFX_TABLE = 0xA05C             # b0, 20 pointer entries
    SFX_COUNT = 20
    SFX_LO, SFX_HI = 0xA000, 0xB000
    SFX_CLEAR = ("b0", 0xA029)     # the tick zeroing the request, not a source

    # LDA #n / STA $1AF8, LDX #n / STX $1AF8, LDY #n / STY $1AF8
    SFX_FORMS = ((0xA9, 0x8D), (0xA2, 0x8E), (0xA0, 0x8C))
    SFX_WHAT = {
        ("f6", 0x507F): "a potion used",
        ("f6", 0x50A3): "a potion used, the auto-use path",
        ("f6", 0x51EE): "item collected",
        ("f6", 0x51FD): "item collected, second variant",
        ("f6", 0x52B8): "a gated item released once the room is cleared",
        ("f6", 0x57A1): "hurting ground",
        ("f6", 0x57A7): "the well of health",
        ("f6", 0x59AB): "projectile impact",
        ("f6", 0x5D97): "a hit the actor survived",
        ("f6", 0x5DB1): "the killing blow",
        ("f6", 0x5FBC): "player contact damage",
        ("f6", 0x5FF0): "player contact damage, tough actor",
        ("f6", 0x603A): "player contact damage, third site",
        ("f6", 0x6676): "a boss hit",
        ("f6", 0x672E): "special-actor contact",
        ("b5", 0xB50B): "a boss hit, bank 5",
        ("b5", 0xBBCA): "Dr. Evil contact",
    }

    def sfx_refs(self):
        """Every site that asks for an effect, and which one it asks for."""
        out = []
        for space in ("b0", "b1", "b2", "b3", "b4", "b5", "b7", "f6", "f7"):
            try:
                base = self.base_of(space)
            except Exception:
                continue
            for off in range(BANK_SIZE - 5):
                a = base + off
                ld = self.byte(space, a)
                forms = [st for im, st in self.SFX_FORMS if im == ld]
                if not forms:
                    continue
                if (self.byte(space, a + 2) != forms[0]
                        or self.byte(space, a + 3) != (self.SFX_REQ & 0xFF)
                        or self.byte(space, a + 4) != (self.SFX_REQ >> 8)):
                    continue
                if (space, a) == self.SFX_CLEAR:
                    continue          # the tick clearing it, not a request
                out.append({"space": space, "at": "%s:$%04X" % (space, a),
                            "addr": a + 1, "id": self.byte(space, a + 1),
                            "what": self.SFX_WHAT.get((space, a), "")})
        return out

    def set_sfx_ref(self, space, addr, sid):
        if not 0 <= int(sid) < self.SFX_COUNT:
            raise EditError("effect id must be $00-$%02X" % (self.SFX_COUNT - 1))
        for r in self.sfx_refs():
            if r["space"] == space and r["addr"] == addr:
                return self.poke(space, addr, int(sid))
        raise EditError("no effect request at %s:$%04X" % (space, addr - 1))

    # The streams sit end to end in one block. Walking it rather than trusting
    # the pointer table matters: three streams in it are referenced by nothing
    # at all, and sizing a stream by the gap to the next *pointed-to* one would
    # quietly offer those bytes up to be overwritten.
    SFX_BLOCK_LO, SFX_BLOCK_HI = 0xA085, 0xA16F

    def _sfx_walk(self):
        """(start, length) for every stream in the block, referenced or not."""
        out, a = [], self.SFX_BLOCK_LO
        while a < self.SFX_BLOCK_HI:
            n = 0
            while a + n < self.SFX_BLOCK_HI and self.byte("b0", a + n) != 0:
                n += 1
            out.append((a, n + 1))            # include the $00
            a += n + 1
        return out

    def _sfx_pointer(self, i):
        return (self.byte("b0", self.SFX_TABLE + 2 * i)
                | (self.byte("b0", self.SFX_TABLE + 2 * i + 1) << 8))

    def _sfx_starts(self):
        return [a for a, _ in self._sfx_walk()]

    def _sfx_bytes(self, at, limit=64):
        out = []
        while len(out) < limit:
            c = self.byte("b0", at + len(out))
            out.append(c)
            if c == 0:
                break
        return out

    def sfx_streams(self):
        """Every stream in the block, and which ids point at each.

        A stream is bounded by the next one, so it can be shortened freely but
        only lengthened into what follows -- which is another stream, not slack.
        """
        walk = self._sfx_walk()
        refs = {}
        for i in range(self.SFX_COUNT):
            refs.setdefault(self._sfx_pointer(i), []).append(i)
        # A stream may grow over anything after it that no id points at -- the
        # three orphans, or the tail left behind by shortening it earlier. It
        # stops at the next stream something actually plays.
        streams = []
        for idx, (a, n) in enumerate(walk):
            end = self.SFX_BLOCK_HI
            for b, _ in walk[idx + 1:]:
                if refs.get(b):
                    end = b
                    break
            streams.append({
                "addr": a, "at": "b0:$%04X" % a, "length": n,
                "capacity": end - a,
                "bytes": [self.byte("b0", a + k) for k in range(n)],
                "used_by": refs.get(a, []),
            })
        effects = []
        for i in range(self.SFX_COUNT):
            a = self._sfx_pointer(i)
            hit = next((s for s in streams if s["addr"] == a), None)
            effects.append({"id": i, "addr": a if hit else None,
                            "at": hit["at"] if hit else None,
                            "used": bool(hit),
                            "shared_with": [j for j in refs.get(a, []) if j != i]
                                           if hit else []})
        return {"effects": effects, "streams": streams,
                "orphans": [s["at"] for s in streams if not s["used_by"]],
                "table": "b0:$%04X" % self.SFX_TABLE,
                "block": "b0:$%04X-$%04X" % (self.SFX_BLOCK_LO,
                                             self.SFX_BLOCK_HI - 1)}

    def set_sfx_stream(self, addr, values):
        """Rewrite one stream in place, addressed by where it starts."""
        for s in self.sfx_streams()["streams"]:
            if s["addr"] != int(addr):
                continue
            v = [int(x) & 0xFF for x in values]
            if not v or v[-1] != 0:
                raise EditError("a stream must end with $00, the byte that "
                                "silences the channel and clears the pointer")
            if 0 in v[:-1]:
                raise EditError("$00 ends the stream, so it can only be the "
                                "last byte")
            if len(v) > s["capacity"]:
                raise EditError("%d bytes will not fit: this stream has %d "
                                "before the next one begins, and the next one "
                                "is another effect, not slack"
                                % (len(v), s["capacity"]))
            # a shorter stream leaves the tail alone: the $00 already ends it
            return self.poke("b0", s["addr"], bytes(v))
        raise EditError("no stream starts at b0:$%04X" % int(addr))

    def set_sfx_pointer(self, sid, addr):
        """Aim an id at another id's stream. Only an existing start is allowed,
        so a pointer can never end up in the middle of a stream or in code."""
        if not 0 <= int(sid) < self.SFX_COUNT:
            raise EditError("effect id must be $00-$%02X" % (self.SFX_COUNT - 1))
        if int(addr) not in self._sfx_starts():
            raise EditError("b0:$%04X is not the start of a stream" % int(addr))
        a = int(addr)
        self.poke("b0", self.SFX_TABLE + 2 * int(sid), bytes([a & 0xFF, a >> 8]))

    # ------------------------------------------------------------ debug hook
    # DbgPauseHook (b0:$BDC2) is called every frame while the console PAUSE
    # switch is held. It counts presses of INPT1 and, at four, refills blood
    # purity and grants +8 hp_max. It can never get there as shipped:
    #
    #   * steps 1 and 2 branch to $BDFA, an orphaned three-instruction run that
    #     reads a different button combination and then falls into $BE00, which
    #     is data. The first byte pair disassembles as PHP / LDX $00FF,Y and
    #     reaches a BRK within seven bytes.
    #   * the two wrong-button exits branch to $BE0E and $BE13, also data, also
    #     reaching a BRK.
    #
    # The IRQ vector is $FF00, the reset entry, so each of those is a soft
    # reboot rather than a hang: the counter can be advanced once and the next
    # invocation restarts the game.
    #
    # The repair is four branch operands and nothing else. Steps 1 and 2 join
    # steps 0 and 3 at the button reader, and the two wrong-button exits go to
    # the RTS at $BDF9 instead of into data. No instruction moves, no byte
    # outside these four changes, and the orphaned run at $BDFA is left alone.
    DEBUG_FIX = [
        # (address of operand, opcode that must precede it, stock, repaired)
        (0xBDCA, 0xF0, 0x2F, 0x1B),      # step 1 -> DbgReadButtons
        (0xBDCE, 0xF0, 0x2B, 0x17),      # step 2 -> DbgReadButtons
        (0xBDED, 0x30, 0x20, 0x0B),      # other button held -> RTS
        (0xBDF1, 0x10, 0x21, 0x07),      # INPT1 not held    -> RTS
    ]

    def debug_hook(self):
        """State of the PAUSE cheat: 'stock', 'repaired', or 'modified'."""
        cur = [self.byte("b0", a) for a, _, _, _ in self.DEBUG_FIX]
        stock = [s for _, _, s, _ in self.DEBUG_FIX]
        fixed = [f for _, _, _, f in self.DEBUG_FIX]
        anchored = all(self.byte("b0", a - 1) == op
                       for a, op, _, _ in self.DEBUG_FIX)
        state = ("stock" if cur == stock else
                 "repaired" if cur == fixed else "modified")
        return {"state": state, "repaired": state == "repaired",
                "anchored": anchored,
                "bytes": [{"at": "b0:$%04X" % (a - 1), "value": v,
                           "stock": s, "fixed": f,
                           "target": (a + 1 + v) & 0xFFFF}
                          for (a, _, s, f), v in zip(self.DEBUG_FIX, cur)]}

    def set_debug_hook(self, repair):
        for a, op, stock, fixed in self.DEBUG_FIX:
            if self.byte("b0", a - 1) != op:
                raise EditError("the opcode at b0:$%04X is no longer $%02X -- "
                                "refusing to write into moved code" % (a - 1, op))
        for a, _, stock, fixed in self.DEBUG_FIX:
            self.poke("b0", a, fixed if repair else stock)

    # ------------------------------------------------- the other palette blocks
    # An area's block (above) colours the terrain, one palette per band. These
    # are the rest: the eight MARIA palettes that colour everything drawn *over*
    # the terrain -- the player, creatures and item icons -- plus the boss sets.
    #
    # Both loaders walk X down from $20 and skip every fourth slot, so palette
    # n's three colours sit at offsets 1 + n*4 and byte 0 of each group is not
    # a colour. The boss sets are the area shape instead: ten groups of four.
    BLOCKS = [
        ("grampa", "b0", 0xA581, 8, "MARIA palettes, live in play",
         "Loaded every time the inventory opens, which in normal play means it "
         "is the one on screen. Item icons pick their palette from the top "
         "three bits of tbl_ItemIconPal."),
        ("intro", "b3", 0x81C9, 8, "MARIA palettes, intro",
         "Loaded once during the intro and then replaced."),
        ("boss1", "b5", 0xB20F, 10, "Boss palette set 1 (Skull)",
         "Ten bands of three, like an area block. Selected by the setup "
         "record's palette index through dat5_B207."),
        ("boss2", "b5", 0xB237, 10, "Boss palette set 2 (Ram)", ""),
        ("boss3", "b5", 0xB25F, 10, "Boss palette set 3 (Dr Evil)", ""),
    ]

    def _block(self, name):
        for n, sp, ad, rows, label, note in self.BLOCKS:
            if n == name:
                return n, sp, self.at(sp, ad), rows, label, note
        raise EditError("no such palette block: %r" % name)

    def icon_palette_users(self):
        """MARIA palette index -> the items drawn with it."""
        names = {1: "cross", 2: "crypt key", 3: "necklace", 4: "heart",
                 5: "plasmic pumpkin", 6: "red potion", 7: "blue potion",
                 8: "diamond", 9: "lantern", 12: "knife", 13: "axe",
                 14: "blaster", 15: "mega blaster"}
        out = {}
        base = self.at("f6", rooms.TBL_ICON_PAL)
        for iid, nm in names.items():
            out.setdefault(self.byte("f6", base + iid) >> 5, []).append(nm)
        return out

    def blocks(self):
        users = self.icon_palette_users()
        out = []
        for n, sp, ad, rows, label, note in self.BLOCKS:
            addr = self.at(sp, ad)
            pals = []
            for i in range(rows):
                pals.append({
                    "index": i,
                    "colours": [self.byte(sp, addr + i * 4 + c) for c in (1, 2, 3)],
                    "used_by": users.get(i, []) if n == "grampa" else [],
                })
            out.append({"name": n, "at": "%s:$%04X" % (sp, addr), "label": label,
                        "note": note, "palettes": pals})
        return out

    def set_block_colour(self, name, index, slot, value):
        """`slot` is 1-3, matching the pixel value that selects it."""
        n, sp, addr, rows, _, _ = self._block(name)
        if not 0 <= index < rows:
            raise EditError("%s has palettes 0-%d" % (name, rows - 1))
        if not 1 <= slot <= 3:
            raise EditError("colour slot must be 1-3; 0 is transparent")
        self.poke(sp, addr + index * 4 + slot, value & 0xFF)

    # -------------------------------------------------------- PAL music timing
    # MusicTick runs exactly once per frame and a note's duration index is a
    # count of frames, so the European cartridge -- which was not retimed --
    # plays everything at 49.92/59.96 = 83.3% speed.
    #
    # Scaling NoteDurTable by 5/6 restores wall-clock tempo without touching a
    # single note. It is pure data and fully reversible, but it is not free:
    # eight of the sixteen entries divide exactly, and the rest round. The
    # melody alternates indices 8 and 11 -- 16 and 8 frames, a clean 2:1 --
    # which become 13 and 7, a ratio 7% off. Long notes land within 1.3%.
    #
    # The exact alternative is to tick the engine six times per five frames,
    # which preserves every ratio, but that needs a counter in RAM and this
    # does not.
    DUR_TABLE = 0x7734
    DUR_LEN = 16
    DUR_STOCK = [0x60, 0x48, 0x40, 0x30, 0x24, 0x20, 0x18, 0x12,
                 0x10, 0x0C, 0x09, 0x08, 0x06, 0x04, 0x03, 0x02]
    PAL_HZ, NTSC_HZ = 49.920395, 59.957873

    def _dur_scaled(self):
        f = self.PAL_HZ / self.NTSC_HZ
        return [max(1, int(round(d * f))) for d in self.DUR_STOCK]

    def music_timing(self):
        base = self.at("f6", self.DUR_TABLE)
        cur = [self.byte("f6", base + i) for i in range(self.DUR_LEN)]
        scaled = self._dur_scaled()
        state = ("stock" if cur == self.DUR_STOCK else
                 "retimed" if cur == scaled else "modified")
        return {"state": state, "retimed": state == "retimed",
                "at": "f6:$%04X" % base, "version": self.version,
                "relevant": self.version == "pal",
                "rows": [{"index": i, "value": cur[i], "stock": self.DUR_STOCK[i],
                          "scaled": scaled[i],
                          "ms_now": round(1000.0 * cur[i] /
                                          (self.PAL_HZ if self.version == "pal"
                                           else self.NTSC_HZ), 1),
                          "ms_ntsc": round(1000.0 * self.DUR_STOCK[i] / self.NTSC_HZ, 1)}
                         for i in range(self.DUR_LEN)]}

    def _pal_only(self, what):
        """Both timing fixes correct a 50 Hz machine. On NTSC they would make
        the music 20% fast, which is the same error in the other direction."""
        if self.version != "pal":
            raise EditError("%s corrects PAL timing and this cartridge is %s. "
                            "Applying it here would make the music run 20%% "
                            "fast." % (what, self.version.upper()))

    def set_music_timing(self, retime):
        if retime:
            self._pal_only("rescaling the duration table")
        base = self.at("f6", self.DUR_TABLE)
        want = self._dur_scaled() if retime else self.DUR_STOCK
        for i, v in enumerate(want):
            self.poke("f6", base + i, v)

    # ------------------------------------------------ exact PAL music timing
    # Rescaling the duration table fixes the tempo but rounds; this fixes the
    # clock instead, and so preserves every ratio exactly.
    #
    # MusicTick has seven call sites across four banks -- b0:$A5BB, b3:$806F
    # and $80A8, f6:$4099, $40EB, $4100, $4B3D and $4BB3 -- so patching call
    # sites is the wrong lever. They all go through the bank 6 entry vector at
    # f6:$4009, which is a single "JMP MusicTick". Redirecting that one vector
    # into a shim covers every path with a two-byte change.
    #
    # The shim runs one extra tick every fifth frame: 6 ticks per 5 PAL frames
    # is 49.920 * 6/5 = 59.90 Hz against NTSC's 59.958, an error of 0.1%.
    #
    #   RETICK:  DEC  counter
    #            BPL  .once
    #            LDA  #$04
    #            STA  counter
    #            JSR  $4009        ; the extra tick
    #   .once:   JMP  $4009        ; the normal one, still a tail call
    #
    # The counter is inventory slot $0A ($1F47). Nothing in the cartridge uses
    # it: no room places item $0A, both Grampa screen loops stop at slot 7
    # (LDX #$07 and AND #$07), and the two DEC/LDA inventory,X sites index by
    # sel_item, which UseSelectedItem caps at 7. Confirmed on the machine with
    # a write tap over four recorded sessions -- eight writes, all inside the
    # first 66 frames from the BIOS memory test and boot, then nothing across
    # ~11,900 frames. A stray starting value only delays the first extra tick;
    # the shim reloads the counter itself.
    #
    # The code goes in the last 16 bytes of bank 6, leaving the rest of the
    # free run at $7F91 for the test-build patcher in tools/patch.py. This one
    # address is deliberately NOT relocated: it is measured from the end of the
    # bank, which is $7FFF in both releases, and the European image's +3 shift
    # is absorbed by that same tail padding.
    RETICK_TAIL = 0x7FF0   # used when the pocket is not open
    RETICK_CTR = 0x1F47
    MUSIC_VECTOR = 0x4009                    # "JMP MusicTick", the one entry
    MUSIC_VEC_OPERAND = 0x400A

    def _music_routine(self):
        """Where the entry vector currently points -- the real MusicTick."""
        o = self.at("f6", self.MUSIC_VEC_OPERAND)
        return self.byte("f6", o) | (self.byte("f6", o + 1) << 8)

    def _retick_code(self, target):
        c, v = self.RETICK_CTR, target
        return bytes([
            0xCE, c & 0xFF, c >> 8,          # DEC counter
            0x10, 0x08,                      # BPL .once
            0xA9, 0x04,                      # LDA #$04
            0x8D, c & 0xFF, c >> 8,          # STA counter
            0x20, v & 0xFF, v >> 8,          # JSR MusicTick
            0x4C, v & 0xFF, v >> 8,          # .once: JMP MusicTick
        ])

    def music_retick(self):
        vec = self._music_routine()
        for at in self.shim_homes(16) + [self.RETICK_TAIL]:
            if vec != at:
                continue
            real = self.byte("f6", at + 11) | (self.byte("f6", at + 12) << 8)
            ok = bytes(self.slice("f6", at, 16)) == self._retick_code(real)
            return {"state": "on" if ok else "modified", "on": ok,
                    "relevant": self.version == "pal", "at": "f6:$%04X" % at,
                    "counter": "$%04X" % self.RETICK_CTR,
                    "vector": "f6:$%04X -> $%04X" % (self.MUSIC_VECTOR, vec),
                    "routine": "$%04X" % real, "bytes": 16}
        return {"state": "off", "on": False, "at": None,
                "relevant": self.version == "pal",
                "counter": "$%04X" % self.RETICK_CTR,
                "vector": "f6:$%04X -> $%04X" % (self.MUSIC_VECTOR, vec),
                "routine": "$%04X" % vec, "bytes": 16}

    def set_music_retick(self, on):
        if on:
            self._pal_only("the extra-tick shim")
        operand = self.at("f6", self.MUSIC_VEC_OPERAND)
        if self.byte("f6", operand - 1) != 0x4C:
            raise EditError("f6:$%04X is no longer a JMP" % (operand - 1))
        cur = self.music_retick()
        if on:
            if cur["on"]:
                return
            code = self._retick_code(self._music_routine())
            at = self._shim_place(code, self.shim_homes(len(code))
                                  + [self.RETICK_TAIL])
            self.poke("f6", at, code)
            self.poke("f6", operand, bytes([at & 0xFF, at >> 8]))
        else:
            if cur["at"] is None:
                return
            at = int(cur["at"].split("$")[1], 16)
            real = self.byte("f6", at + 11) | (self.byte("f6", at + 12) << 8)
            self.poke("f6", operand, bytes([real & 0xFF, real >> 8]))
            self.poke("f6", at, bytes(16))

    # ------------------------------------------------------------------ music
    # Three levels: a song table of two track pointers per song, tracks of
    # pattern pointers ending in a terminator, and patterns of a count byte
    # followed by that many two-byte notes.
    #
    #   byte 0   instrument (high nibble) | duration index (low nibble)
    #   byte 1   waveform (top 3 bits) | frequency (low 5 bits); 0 is a rest
    #
    # AUDF is a five-bit register: the player writes the whole byte, the chip
    # keeps bits 0-4, and the engine shifts the same byte right by five to pick
    # the waveform from the three bits the chip threw away. So one byte carries
    # timbre and pitch together, and editing pitch means keeping the top bits.
    #
    # Patterns are packed end to end, so a note's *values* can change but the
    # count cannot -- adding one would push every following pattern along.
    SONG_TABLE = 0x7F65
    N_SONGS = 12
    SONG_NAMES = {
        0: "intro, first cue", 1: "main theme (chains to 2)",
        2: "main theme part 2 (chains to 1)", 3: "Grampa screen",
        4: "title screen (loops)", 5: "boss fight", 6: "intro, second cue",
        7: "boss defeated", 8: "cave music (area pages 3, 4, 8)",
        9: "cave music (area page 7)", 10: "the funeral dirge",
        11: "silence",
    }
    SONG_BANK = {0: 3, 3: 0, 4: 3, 5: 5, 6: 3}

    def _mread(self, addr, bank):
        """One byte as the running game would see it."""
        if 0x4000 <= addr < 0x8000:
            return self.byte("f6", addr)
        if addr >= 0xC000:
            return self.byte("f7", addr)
        if 0x8000 <= addr < 0xC000:
            if bank is None:
                raise EditError("$%04X is in the paged window and this song's "
                                "bank is not known" % addr)
            return self.byte("b%d" % bank, addr)
        raise EditError("$%04X is RAM, not ROM" % addr)

    def _mspace(self, addr, bank):
        if 0x4000 <= addr < 0x8000:
            return "f6"
        if addr >= 0xC000:
            return "f7"
        return "b%d" % bank

    def songs(self):
        base = self.at("f6", self.SONG_TABLE)
        out = []
        for n in range(self.N_SONGS):
            bank = self.SONG_BANK.get(n)
            a = base + n * 4
            voices = []
            for v in (0, 2):
                ptr = self.byte("f6", a + v) | (self.byte("f6", a + v + 1) << 8)
                voices.append(self._voice(ptr, bank))
            out.append({"song": n, "name": self.SONG_NAMES.get(n, ""),
                        "bank": bank, "at": "f6:$%04X" % a, "voices": voices})
        return out

    def _voice(self, ptr, bank):
        if not ptr:
            return {"ptr": 0, "patterns": [], "terminator": None, "error": None}
        try:
            pats, term, p = [], None, ptr
            while len(pats) < 64:
                lo = self._mread(p, bank)
                hi = self._mread(p + 1, bank)
                if hi == 0:
                    term = lo
                    break
                pats.append(lo | (hi << 8))
                p += 2
            out = []
            for pa in pats:
                cnt = self._mread(pa, bank)
                notes = []
                for i in range(cnt):
                    na = pa + 1 + i * 2
                    b0 = self._mread(na, bank)
                    b1 = self._mread(na + 1, bank)
                    notes.append({
                        "at": na, "space": self._mspace(na, bank),
                        "b0": b0, "b1": b1,
                        "instrument": b0 >> 4, "dur": b0 & 0x0F,
                        "frames": self.byte("f6", self.at("f6", self.DUR_TABLE)
                                            + (b0 & 0x0F)),
                        "wave": b1 >> 5, "pitch": b1 & 0x1F, "rest": b1 == 0,
                    })
                out.append({"at": "$%04X" % pa, "count": cnt, "notes": notes})
            return {"ptr": ptr, "patterns": out, "terminator": term, "error": None}
        except EditError as e:
            return {"ptr": ptr, "patterns": [], "terminator": None,
                    "error": str(e)}

    def set_note(self, space, addr, instrument=None, dur=None,
                 wave=None, pitch=None, rest=None):
        b0 = self.byte(space, addr)
        b1 = self.byte(space, addr + 1)
        if instrument is not None:
            if not 0 <= instrument <= 15:
                raise EditError("instrument is a nibble: 0-15")
            b0 = (b0 & 0x0F) | (instrument << 4)
        if dur is not None:
            if not 0 <= dur <= 15:
                raise EditError("duration index is a nibble: 0-15")
            b0 = (b0 & 0xF0) | dur
        if rest:
            b1 = 0
        else:
            if wave is not None:
                if not 0 <= wave <= 7:
                    raise EditError("waveform is three bits: 0-7")
                b1 = (b1 & 0x1F) | (wave << 5)
            if pitch is not None:
                if not 0 <= pitch <= 31:
                    raise EditError("AUDF is five bits: pitch is 0-31")
                b1 = (b1 & 0xE0) | pitch
        self.poke(space, addr, bytes([b0, b1]))

    # ---------------------------------------------------------------- patches
    # A patch carries only the bytes that differ, plus CRC32 of the ROM it was
    # made from, the ROM it produces, and itself. See tools/bps.py for why BPS
    # rather than IPS: IPS records offsets and data and verifies nothing, so a
    # patch applied to the wrong cartridge silently corrupts it.
    # A patch is built against the cartridge data alone, with the 128-byte .a78
    # header left out. The header is not part of the ROM -- it describes the
    # file to an emulator -- and the same dump ships behind different ones: our
    # Europe image and Trebor's PAL hold identical data but declare different
    # cart types, so a header-inclusive patch made on one is refused by the
    # other for no reason that matters. Patching the body makes one patch serve
    # both, and the header of whatever image it is applied to is kept.
    #
    # Patches written before this still load: they are recognised by declaring
    # a source 128 bytes longer than the ROM, and applied the old way.
    def export_patch(self, path, note=""):
        if not self.dirty():
            raise EditError("nothing has changed, so there is nothing to patch")
        meta = (note or "Midnight Mutants editor, %s layout" % self.version)
        blob = bps.create(bytes(self.original), bytes(self.rom),
                          meta.encode("utf-8")[:255])
        with open(path, "wb") as f:
            f.write(blob)
        return {"path": path, "size": len(blob), "headerless": True,
                "changed": len(self.changes()), "note": meta}

    def _file_bytes(self, rom):
        """The image as it exists on disk, a78 header included."""
        return (self.header or b"") + bytes(rom)

    def _patch_source(self, header):
        """What a patch of that shape was built against."""
        if header["source_size"] == len(self.original):
            return bytes(self.original), False        # body only, portable
        return self._file_bytes(self.original), True  # legacy, header included

    def patch_info(self, path):
        with open(path, "rb") as f:
            blob = f.read()
        h = bps.read_header(blob)
        src, legacy = self._patch_source(h)
        mine = zlib.crc32(src)
        return {"size": len(blob), "source_size": h["source_size"],
                "target_size": h["target_size"],
                "source_crc": "$%08X" % h["source_crc"],
                "target_crc": "$%08X" % h["target_crc"],
                "note": h["metadata"].decode("utf-8", "replace"),
                "matches": h["source_crc"] == mine,
                "headerless": not legacy,
                "your_crc": "$%08X" % mine}

    def import_patch(self, path, force=False):
        """Apply a patch over the *unedited* image, replacing current edits."""
        with open(path, "rb") as f:
            blob = f.read()
        h = bps.read_header(blob)
        src, legacy = self._patch_source(h)
        out, warn = bps.apply(src, blob, strict=not force)
        body = out[len(self.header or b""):] if legacy else out
        if len(body) != len(self.original):
            raise EditError("the patch produces a %d-byte ROM; this one is %d"
                            % (len(body), len(self.original)))
        if legacy:
            warn = list(warn) + ["this patch includes the .a78 header, so it "
                                 "only fits the exact file it was made from; "
                                 "re-export it to get one that fits any header"]
        self.rom = bytearray(body)
        return {"warnings": warn, "changed": len(self.changes()),
                "headerless": not legacy}

    # -------------------------------------------------- water walk by terrain
    # As shipped the necklace crossing is a position test, not a terrain test.
    # f7:$D0C0 sets ram_1FA9 only when the necklace is the selected item, the
    # room is $01, and the player stands inside a fixed rectangle -- and
    # f6:$5666 reads that flag where blocking terrain would otherwise stop
    # them. So the fountain in the first room is crossable and identical water
    # anywhere else is not.
    #
    # Bit 2 of a terrain byte marks water and the engine never tests it: the
    # collision check is only AND #$03. This patch gives that bit its obvious
    # meaning. At the point where the terrain has decided to block, a shim asks
    # two more questions -- is this square water, and is the necklace the
    # selected item -- and lets the player through if both hold. The original
    # rectangle still works, so nothing that used to be crossable stops being.
    #
    #   $7FD0  LDA $1FA9      the original room-$01 rectangle
    #          BNE allow
    #          LDA $4F        the terrain byte that just blocked
    #          AND #$04       water?
    #          BEQ block
    #          LDA $CC        sel_item
    #          CMP #$03       the necklace, selected rather than carried
    #          BNE block
    #   allow: CLC / RTS
    #   block: SEC / RTS
    #
    # It goes at $7FD0, clear of the test-build patcher at $7F91 and the music
    # shim at $7FF0, and like those is measured from the end of the bank rather
    # than relocated.
    WATER_TAIL = 0x7FD0    # used when the pocket is not open
    WATER_SITE = 0x5666            # "LDA ram_1FA9" at the blocking decision
    WATER_CODE = bytes([
        0xAD, 0xA9, 0x1F,          # LDA $1FA9
        0xD0, 0x0C,                # BNE allow
        0xA5, 0x4F,                # LDA terrain_byte
        0x29, 0x04,                # AND #$04
        0xF0, 0x08,                # BEQ block
        0xA5, 0xCC,                # LDA sel_item
        0xC9, 0x03,                # CMP #$03
        0xD0, 0x02,                # BNE block
        0x18, 0x60,                # allow: CLC / RTS
        0x38, 0x60,                # block: SEC / RTS
    ])
    WATER_STOCK = bytes([0xAD, 0xA9, 0x1F])

    def water_walk(self):
        site = self.at("f6", self.WATER_SITE)
        here = bytes(self.slice("f6", site, 3))
        if here == self.WATER_STOCK:
            return {"state": "off", "on": False, "at": None,
                    "site": "f6:$%04X" % site, "bytes": len(self.WATER_CODE)}
        if here[0] == 0x4C:
            at = here[1] | (here[2] << 8)
            on = bytes(self.slice("f6", at, len(self.WATER_CODE))) == self.WATER_CODE
            return {"state": "on" if on else "modified", "on": on,
                    "at": "f6:$%04X" % at, "site": "f6:$%04X" % site,
                    "bytes": len(self.WATER_CODE)}
        return {"state": "modified", "on": False, "at": None,
                "site": "f6:$%04X" % site, "bytes": len(self.WATER_CODE)}

    def set_water_walk(self, on):
        site = self.at("f6", self.WATER_SITE)
        here = bytes(self.slice("f6", site, 3))
        cur = self.water_walk()
        if on:
            if cur["on"]:
                return
            if here != self.WATER_STOCK:
                raise EditError("f6:$%04X is not the instruction this replaces"
                                % site)
            at = self._shim_place(self.WATER_CODE,
                                  self.shim_homes(len(self.WATER_CODE))
                                  + [self.WATER_TAIL])
            self.poke("f6", at, self.WATER_CODE)
            self.poke("f6", site, bytes([0x4C, at & 0xFF, at >> 8]))
        else:
            if not cur["at"]:
                return
            at = int(cur["at"].split("$")[1], 16)
            self.poke("f6", at, bytes(len(self.WATER_CODE)))
            self.poke("f6", site, self.WATER_STOCK)

    # ------------------------------------------------- the compacted flip
    # sub_44EC picks the display double buffer and writes ten display-list high
    # bytes for it. Each branch does that as ten LDA#/STA pairs although the
    # value changes only twice, so loading each distinct value once frees 28
    # bytes without altering a single write.
    #
    # The freed bytes stay where they are rather than closing the gap: dat_455C
    # follows immediately and four banks point into it.
    #
    # Confirmed in play over a 22,215-frame session ending with the Ram boss
    # beaten -- the display list holds a valid pattern throughout, the buffers
    # alternate 17,002 times, and nothing writes into the freed bytes. The stock
    # cartridge shows the same isolated single-frame samples during play (22
    # against 31), so those are the game's own behaviour, not the change's.
    #
    # Cycle count does change, and the random generator mixes scratch RAM, so a
    # compacted cartridge takes a different random path from the same inputs.
    # Different, not broken.
    FLIP_AT = 0x44EC
    FLIP_LEN = 112
    FLIP_STOCK = bytes([
        0xA5, 0xD0, 0x49, 0x01, 0x29, 0x01, 0x85, 0xD0, 0xF0, 0x33, 0xA9, 0x18,
        0x8D, 0x23, 0x21, 0xA9, 0x18, 0x8D, 0x24, 0x21, 0xA9, 0x18, 0x8D, 0x25,
        0x21, 0xA9, 0x18, 0x8D, 0x26, 0x21, 0xA9, 0x19, 0x8D, 0x27, 0x21, 0xA9,
        0x19, 0x8D, 0x28, 0x21, 0xA9, 0x19, 0x8D, 0x29, 0x21, 0xA9, 0x1A, 0x8D,
        0x2A, 0x21, 0xA9, 0x1A, 0x8D, 0x2B, 0x21, 0xA9, 0x1A, 0x8D, 0x2C, 0x21,
        0x60, 0xA9, 0x1B, 0x8D, 0x23, 0x21, 0xA9, 0x1B, 0x8D, 0x24, 0x21, 0xA9,
        0x1B, 0x8D, 0x25, 0x21, 0xA9, 0x1B, 0x8D, 0x26, 0x21, 0xA9, 0x1C, 0x8D,
        0x27, 0x21, 0xA9, 0x1C, 0x8D, 0x28, 0x21, 0xA9, 0x1C, 0x8D, 0x29, 0x21,
        0xA9, 0x1D, 0x8D, 0x2A, 0x21, 0xA9, 0x1D, 0x8D, 0x2B, 0x21, 0xA9, 0x1D,
        0x8D, 0x2C, 0x21, 0x60])
    FLIP_COMPACT = bytes([
        0xA5, 0xD0, 0x49, 0x01, 0x29, 0x01, 0x85, 0xD0, 0xF0, 0x25, 0xA9, 0x18,
        0x8D, 0x23, 0x21, 0x8D, 0x24, 0x21, 0x8D, 0x25, 0x21, 0x8D, 0x26, 0x21,
        0xA9, 0x19, 0x8D, 0x27, 0x21, 0x8D, 0x28, 0x21, 0x8D, 0x29, 0x21, 0xA9,
        0x1A, 0x8D, 0x2A, 0x21, 0x8D, 0x2B, 0x21, 0x8D, 0x2C, 0x21, 0x60, 0xA9,
        0x1B, 0x8D, 0x23, 0x21, 0x8D, 0x24, 0x21, 0x8D, 0x25, 0x21, 0x8D, 0x26,
        0x21, 0xA9, 0x1C, 0x8D, 0x27, 0x21, 0x8D, 0x28, 0x21, 0x8D, 0x29, 0x21,
        0xA9, 0x1D, 0x8D, 0x2A, 0x21, 0x8D, 0x2B, 0x21, 0x8D, 0x2C, 0x21, 0x60])
    POCKET_AT = 0x4540
    POCKET_LEN = 28

    def compact_flip(self):
        at = self.at("f6", self.FLIP_AT)
        # only the routine decides this; whatever sits in the pocket afterwards
        # is a separate question, and normally it is a patch we put there
        here = bytes(self.slice("f6", at, len(self.FLIP_COMPACT)))
        on = here == self.FLIP_COMPACT
        return {"state": "on" if on else
                         "off" if bytes(self.slice("f6", at, self.FLIP_LEN))
                                  == self.FLIP_STOCK else "modified",
                "on": on, "at": "f6:$%04X" % at,
                "pocket": "f6:$%04X" % self.at("f6", self.POCKET_AT),
                "frees": self.POCKET_LEN}

    def set_compact_flip(self, on):
        at = self.at("f6", self.FLIP_AT)
        here = bytes(self.slice("f6", at, self.FLIP_LEN))
        want = (self.FLIP_COMPACT + bytes(self.POCKET_LEN)) if on else self.FLIP_STOCK
        if here == want:
            return
        if not on:
            pocket = self.at("f6", self.POCKET_AT)
            if any(self.byte("f6", pocket + i) for i in range(self.POCKET_LEN)):
                raise EditError("a patch is installed in the pocket at f6:$%04X "
                                "-- turn it off before restoring the original "
                                "routine" % pocket)
        if here not in (self.FLIP_STOCK, self.FLIP_COMPACT + bytes(self.POCKET_LEN)):
            raise EditError("f6:$%04X does not hold either form of the flip "
                            "routine -- refusing to overwrite it" % at)
        self.poke("f6", at, want)

    # ---------------------------------------------------------- shim homes
    # A code patch goes wherever it fits, preferring the pocket the compacted
    # flip opens so the tail of bank 6 stays whole for the test-build patcher.
    def shim_homes(self, size):
        """Addresses this patch could live at, best first."""
        out = []
        if self.compact_flip()["on"] and size <= self.POCKET_LEN:
            out.append(self.at("f6", self.POCKET_AT))
        return out

    def _shim_find(self, code, homes):
        """Where this shim currently is, or None."""
        for a in homes:
            if bytes(self.slice("f6", a, len(code))) == code:
                return a
        return None

    def _shim_place(self, code, homes):
        """Somewhere free and big enough, preferring the earlier candidates."""
        for a in homes:
            if bytes(self.slice("f6", a, len(code))) == bytes(len(code)):
                return a
        raise EditError("no free space for a %d-byte patch: the pocket and the "
                        "tail are both occupied" % len(code))

    # ------------------------------------------------------- the free run
    # Bank 6 ends with a run of $00 that anything appending code has to share:
    # the test-build patcher starts at the bottom of it and the editor's shims
    # take what they need. Compacting the display flip opens a second, separate
    # pocket, and shims prefer it so the tail stays whole for the patcher.
    FREE_BASE = 0x7F91
    FREE_END = 0x8000

    def free_space(self):
        base = self.at("f6", self.FREE_BASE)
        # The largest unbroken run of $00 anywhere in the tail, not just the one
        # starting at the base. Counting only from the base reports zero the
        # moment the test-build patcher takes the first byte, which made a
        # cartridge with 93 bytes still free look completely full.
        run, cur, gap_at, best_at = 0, 0, base, base
        for a in range(base, self.FREE_END):
            if self.byte("f6", a) == 0:
                if cur == 0:
                    gap_at = a
                cur += 1
                if cur > run:
                    run, best_at = cur, gap_at
            else:
                cur = 0
        total_free = sum(1 for a in range(base, self.FREE_END)
                         if self.byte("f6", a) == 0)
        occupants = []
        hint = self.pumpkin_hint()
        for name, info, size in (("water walk", self.water_walk(),
                                  len(self.WATER_CODE)),
                                 ("music retick", self.music_retick(), 16),
                                 ("pumpkin hint", hint, hint["bytes"] or 61)):
            occupants.append({"name": name, "bytes": size,
                              "installed": info["on"], "at": info["at"] or "-"})
        used = sum(o["bytes"] for o in occupants if o["installed"])
        flip = self.compact_flip()
        pocket = self.at("f6", self.POCKET_AT)
        free_pocket = flip["on"] and all(
            self.byte("f6", pocket + i) == 0 for i in range(self.POCKET_LEN))
        return {"at": "f6:$%04X" % base, "total": self.FREE_END - base,
                "contiguous": run, "largest_at": "f6:$%04X" % best_at,
                "free_total": total_free, "used": used,
                "pocket_open": flip["on"], "pocket_free": free_pocket,
                "pocket_at": "f6:$%04X" % pocket,
                "pocket_bytes": self.POCKET_LEN,
                "occupants": occupants, "patcher_min": 4}

    # --------------------------------------------------- the reticle leg
    # The last frame of the special-actor death animation draws four 8-pixel
    # fragments, and the fourth names gfx $EE -- which is the eight pixels the
    # Grampa screen uses for its item-select reticle. So a UI element appears
    # briefly as the corpse's right leg. It is in the data, not a misreading:
    #
    #   f6:$49EA  E0                     page $E0
    #             FE EF E8 FB            fragment, gfx $E8
    #             FE 19 EA FB            fragment, gfx $EA
    #             BE F2 EC 0E            fragment, gfx $EC   the left leg
    #             BE 16 EE 0E            fragment, gfx $EE   <- the reticle
    #             00
    #
    # The artwork has no fourth melt fragment: $EC and $EE are the two halves of
    # one 16-pixel cell, and the right half is the reticle. So the repair points
    # the fourth fragment at $EC as well, giving the corpse two of the same melt
    # piece instead of a targeting bracket. One byte, and it changes nothing but
    # which eight pixels are fetched.
    RETICLE_AT = 0x49F9            # the gfx byte of the fourth fragment
    RETICLE_STOCK = 0xEE
    RETICLE_FIXED = 0xEC

    def reticle_leg(self):
        at = self.at("f6", self.RETICLE_AT)
        v = self.byte("f6", at)
        return {"state": "fixed" if v == self.RETICLE_FIXED else
                         "stock" if v == self.RETICLE_STOCK else "modified",
                "fixed": v == self.RETICLE_FIXED, "value": v,
                "at": "f6:$%04X" % at}

    def set_reticle_leg(self, fix):
        at = self.at("f6", self.RETICLE_AT)
        v = self.byte("f6", at)
        if v not in (self.RETICLE_STOCK, self.RETICLE_FIXED):
            raise EditError("f6:$%04X holds $%02X, neither the reticle nor the "
                            "repair -- refusing to overwrite it" % (at, v))
        self.poke("f6", at, self.RETICLE_FIXED if fix else self.RETICLE_STOCK)

    # ------------------------------------------- the selected-item icon
    # sub_681B draws the icon in the status bar for whatever is selected, from
    # two tables indexed by sel_item: gfx at f6:$6838 and palette|width at
    # f6:$6845. Three entries are wrong, and the game shows it during play.
    #
    #   MARIA palette 5 is $00 $11 $14 -- colour 1 is pure black.
    #
    #   crypt key  gfx $D6, palette 5.  Its 30 lit pixels are ALL colour 1, so
    #              it renders entirely black: invisible on the status bar.
    #   necklace   gfx $D2, palette 5.  22 pixels colour 1 (black) and 13
    #              colour 2 ($11, nearly black): barely visible.
    #   pumpkin    gfx $D0 -- which is the *heart's* icon. The pumpkin's own
    #              icon is $F4, as the room-item table at f6:$5195 has it.
    #
    # The weapons in the same tables use palette 4 ($1A $22 $0D), whose colour 1
    # is a light gold, and they read clearly. So the repair moves the two
    # invisible items to palette 4 and points the pumpkin at its own artwork.
    ICON_GFX = 0x6838              # indexed by sel_item
    ICON_PAL = 0x6845
    ICON_FIXES = [
        ("crypt key", ICON_PAL, 2, 0xBE, 0x9E, "palette 5 -> 4, so it is not black"),
        ("necklace", ICON_PAL, 3, 0xBE, 0x9E, "palette 5 -> 4, so it is not black"),
        ("plasmic pumpkin", ICON_GFX, 5, 0xD0, 0xF4, "the heart's icon -> its own"),
        ("plasmic pumpkin", ICON_PAL, 5, 0xBE, 0x9E, "palette 5 -> 4, so it is lit"),
    ]

    def icon_fixes(self):
        out = []
        for name, tbl, idx, stock, fixed, why in self.ICON_FIXES:
            at = self.at("f6", tbl) + idx
            v = self.byte("f6", at)
            out.append({"name": name, "at": "f6:$%04X" % at, "value": v,
                        "stock": stock, "fixed": fixed, "why": why,
                        "is_fixed": v == fixed})
        done = [x["is_fixed"] for x in out]
        return {"entries": out, "fixed": all(done),
                "state": "fixed" if all(done) else
                         "stock" if not any(done) else "partial"}

    def set_icon_fixes(self, fix):
        for name, tbl, idx, stock, fixed, why in self.ICON_FIXES:
            at = self.at("f6", tbl) + idx
            v = self.byte("f6", at)
            if v not in (stock, fixed):
                raise EditError("f6:$%04X holds $%02X, neither the stock value "
                                "nor the repair -- refusing to overwrite it"
                                % (at, v))
            self.poke("f6", at, fixed if fix else stock)

    # ------------------------------------- the ordinary actor's first death frame
    # The same defect as the ghost, in the animation every crow, bat and ground
    # enemy plays. sub_5BCC picks the frame with
    #
    #     LDA actor_mode,X : TAY : LDA dat_5CE6,Y
    #
    # using the mode *directly* as the index, and the kill at f6:$5DAD seeds it
    # with $08. dat_5CE6 holds eight entries, $5CE6 to $5CED, and sub_5CEE
    # begins immediately after -- so the first frame reads that routine's $A5
    # opcode and draws sprite $A5, a misaligned slice of the blaster artwork.
    #
    # Seeding $07 keeps every index inside the table. The only comparisons of
    # actor_mode anywhere are against $A0, the damage threshold, so nothing else
    # depends on the value; the animation simply runs seven ticks instead of
    # eight.
    ACTOR_SEED = 0x5DAE                   # the operand of LDA #$08
    ACTOR_STOCK, ACTOR_FIXED = 0x08, 0x07
    ACTOR_TABLE, ACTOR_ENTRIES = 0x5CE6, 8

    def actor_death(self):
        at = self.at("f6", self.ACTOR_SEED)
        v = self.byte("f6", at)
        tbl = self.at("f6", self.ACTOR_TABLE)
        bad = [{"mode": "$%02X" % st, "index": st,
                "sprite": "$%02X" % self.byte("f6", tbl + st)}
               for st in range(v, 0, -1) if st >= self.ACTOR_ENTRIES]
        return {"at": "f6:$%04X" % at, "seed": "$%02X" % v,
                "table": "f6:$%04X" % tbl, "entries": self.ACTOR_ENTRIES,
                "fixed": v == self.ACTOR_FIXED,
                "state": "fixed" if v == self.ACTOR_FIXED else
                         "stock" if v == self.ACTOR_STOCK else "modified",
                "overruns": bad, "frames": v, "bytes": 1}

    def set_actor_death(self, fix):
        at = self.at("f6", self.ACTOR_SEED)
        v = self.byte("f6", at)
        if v not in (self.ACTOR_STOCK, self.ACTOR_FIXED):
            raise EditError("f6:$%04X holds $%02X, neither the stock seed nor "
                            "the repair -- refusing to overwrite it" % (at, v))
        if self.byte("f6", at - 1) != 0xA9:
            raise EditError("f6:$%04X is no longer an LDA immediate" % (at - 1))
        self.poke("f6", at, self.ACTOR_FIXED if fix else self.ACTOR_STOCK)

    # ---------------------------------------------- the ghost's first death frame
    # A dying ghost counts ram_1EB3 down and picks its picture with
    #
    #     LDA ram_1EB3,X : LSR A : TAY : LDA dat_6219,Y
    #
    # so the index is the state halved. The kill at f6:$6268 seeds the state
    # with $10, and $10 >> 1 is 8 -- but dat_6219 holds eight entries, $6219 to
    # $6220, and sub_6221 begins immediately after. The first frame therefore
    # reads $6221, the $A5 opcode of that routine, and draws sprite $A5.
    #
    # The ghost is 16 pixels wide and drawn as a top half plus top + $20, so
    # that frame shows a misaligned slice of the mega blaster's orb over a
    # misaligned slice of the AWESOME lettering. Every later state indexes 7 or
    # below and is correct.
    #
    # Seeding $0F instead keeps the index inside the table. Nothing else tests
    # the value: the four other reads of ram_1EB3 are sign or zero tests, so
    # the only effect is that the animation is one tick shorter.
    GHOST_SEED = 0x6269                   # the operand of LDA #$10
    GHOST_STOCK, GHOST_FIXED = 0x10, 0x0F
    GHOST_TABLE, GHOST_ENTRIES = 0x6219, 8

    def ghost_death(self):
        at = self.at("f6", self.GHOST_SEED)
        v = self.byte("f6", at)
        tbl = self.at("f6", self.GHOST_TABLE)
        seq = []
        for st in range(v, 0, -1):
            i = st >> 1
            seq.append({"state": "$%02X" % st, "index": i,
                        "sprite": "$%02X" % self.byte("f6", tbl + i),
                        "past": i >= self.GHOST_ENTRIES})
        return {"at": "f6:$%04X" % at, "seed": "$%02X" % v,
                "table": "f6:$%04X" % tbl, "entries": self.GHOST_ENTRIES,
                "fixed": v == self.GHOST_FIXED,
                "state": "fixed" if v == self.GHOST_FIXED else
                         "stock" if v == self.GHOST_STOCK else "modified",
                "overruns": [f for f in seq if f["past"]],
                "frames": len(seq), "bytes": 1}

    def set_ghost_death(self, fix):
        at = self.at("f6", self.GHOST_SEED)
        v = self.byte("f6", at)
        if v not in (self.GHOST_STOCK, self.GHOST_FIXED):
            raise EditError("f6:$%04X holds $%02X, neither the stock seed nor "
                            "the repair -- refusing to overwrite it" % (at, v))
        if self.byte("f6", at - 1) != 0xA9:
            raise EditError("f6:$%04X is no longer an LDA immediate" % (at - 1))
        self.poke("f6", at, self.GHOST_FIXED if fix else self.GHOST_STOCK)

    # -------------------------------------------- a fourth pose for the axe
    # With the tumble on, the axe's run reads $CE $BC $BE $BC -- four phases
    # over three drawings, so one pose shows twice. Page $E0 has room: the six
    # bytes at $88-$8D are referenced by nothing at all (see SPRITES.md), and an
    # axe sprite is two bytes wide, so $88 is a free slot.
    #
    # Mirroring $CE into it and pointing the duplicated phase there gives four
    # distinct orientations for one table byte and 32 bytes of artwork. It only
    # shows with the tumble on: without it the phase never leaves 0.
    AXE4_LOW = 0x88                       # the free sprite slot on page $E0
    AXE4_SLOT = 0x4FAE + 0x1B             # the phase that repeats $BC
    AXE4_STOCK = bytes([
        0x00, 0x04, 0x00, 0x05, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01,
        0x00, 0x02, 0x0C, 0x00, 0x03, 0xFF, 0x00, 0x08, 0x00, 0x08, 0x00, 0x08,
        0x00, 0x20, 0x00, 0x20, 0x00, 0x80, 0x00, 0x00])
    AXE4_ART = bytes([
        0x20, 0x00, 0x28, 0x00, 0x08, 0x00, 0x08, 0x00, 0x0A, 0x3C, 0x02, 0x0F,
        0x02, 0x0F, 0x02, 0xBF, 0x00, 0xBF, 0x30, 0xFF, 0x3F, 0xF3, 0x3F, 0xE0,
        0x3F, 0x28, 0x3C, 0x00, 0x0F, 0x00, 0x0F, 0x00])

    def _axe4_cells(self):
        """(address, address) per line -- graphics are line-planar, so a sprite
        is one column through consecutive pages, the first line highest."""
        out = []
        for ln in range(rooms.CHAR_H):
            base = (rooms.ICON_PAGE + (rooms.CHAR_H - 1 - ln)) << 8
            out.append((base | self.AXE4_LOW, base | (self.AXE4_LOW + 1)))
        return out

    def _axe4_art(self):
        return bytes(b for a in self._axe4_cells() for b in
                     (self.byte("f7", a[0]), self.byte("f7", a[1])))

    def axe_fourth(self):
        art = self._axe4_art()
        slot = self.at("f6", self.AXE4_SLOT)
        pointed = self.byte("f6", slot) == self.AXE4_LOW
        return {"at": "f7:$E0%02X" % self.AXE4_LOW, "slot": "f6:$%04X" % slot,
                "run": ["$%02X" % self.byte("f6", self.at("f6", 0x4FAE) + 0x18 + i)
                        for i in range(4)],
                "on": pointed and art == self.AXE4_ART,
                "state": "on" if (pointed and art == self.AXE4_ART) else
                         "off" if (not pointed and art == self.AXE4_STOCK) else
                         "modified",
                "needs_spin": True, "bytes": 33}

    def set_axe_fourth(self, on):
        art = self._axe4_art()
        slot = self.at("f6", self.AXE4_SLOT)
        here = self.byte("f6", slot)
        if art not in (self.AXE4_STOCK, self.AXE4_ART):
            raise EditError("f7:$E0%02X no longer holds either the stock bytes "
                            "or the mirrored axe -- refusing to overwrite it"
                            % self.AXE4_LOW)
        if here not in (0xBC, self.AXE4_LOW):
            raise EditError("f6:$%04X is neither the stock frame nor the "
                            "repair" % slot)
        want = self.AXE4_ART if on else self.AXE4_STOCK
        for ln, (a, b) in enumerate(self._axe4_cells()):
            self.poke("f7", a, want[ln * 2])
            self.poke("f7", b, want[ln * 2 + 1])
        self.poke("f6", slot, self.AXE4_LOW if on else 0xBC)

    # ------------------------------------------ the mega blaster's lost frames
    # The mega blaster asks for four phases and its run reads $A4 $A6 $A4 $A6 --
    # two pictures shown twice. But $A8 and $AA hold two more frames of the same
    # glowing orb, 65 and 74 lit pixels, with the bright core in a different
    # place. Nothing on page $E0 names them: not the projectile tables, not any
    # composite record, not either icon table. (dat_6440 does hold those values,
    # but that table feeds the special-actor slot, which f6:$65B1 gives page
    # $C0 -- different page, different artwork.)
    #
    # So the animation was drawn and never wired. Pointing the last two phases
    # at it costs two bytes and needs no new art.
    MEGA_RUN = 0x4FAE + 0x22              # phases 2 and 3 of the mega's run
    MEGA_STOCK = bytes([0xA4, 0xA6])
    MEGA_FULL = bytes([0xA8, 0xAA])

    def mega_frames(self):
        at = self.at("f6", self.MEGA_RUN)
        here = bytes(self.slice("f6", at, 2))
        return {"at": "f6:$%04X" % at,
                "run": ["$%02X" % self.byte("f6", self.at("f6", 0x4FAE) + 0x20 + i)
                        for i in range(4)],
                "on": here == self.MEGA_FULL,
                "state": "on" if here == self.MEGA_FULL else
                         "off" if here == self.MEGA_STOCK else "modified",
                "bytes": 2}

    def set_mega_frames(self, on):
        at = self.at("f6", self.MEGA_RUN)
        here = bytes(self.slice("f6", at, 2))
        if here not in (self.MEGA_STOCK, self.MEGA_FULL):
            raise EditError("f6:$%04X is neither the stock run nor the repair "
                            "-- refusing to overwrite it" % at)
        self.poke("f6", at, self.MEGA_FULL if on else self.MEGA_STOCK)

    # ------------------------------------------------- the axe never tumbles
    # A projectile draws dat_4FAE[dat_4F9E[type] + phase], and the phase counts
    # down from dat_4FD2[type]. That last table is a frame count, not a
    # graphic: the knife asks for 6, both blasters for 4, and the axe for
    # **one** -- so the axe shows a single sprite for its whole flight and
    # appears to slide.
    #
    # The art is already there. Its four entries sit together at index $18 as
    # $CE $BC $BE $BC -- three orientations, one per facing with down and right
    # sharing -- so pointing every facing at that run and asking for four
    # phases makes it turn over. Nothing new is drawn.
    #
    # The other facings cannot keep their own window: base $19 plus three
    # phases runs off the end of the axe run into the blaster's $A0. So all
    # four read base $18, which trades the per-facing orientation for motion.
    #
    # The step gate reads $44, a counter incremented every frame, so a step
    # lasts two frames. $45 is incremented every *other* frame (f6:$40B4), so
    # reading that instead halves the rate. It is one byte and it is shared:
    # the knife and both blasters slow with it.
    AXE_BASE, AXE_FRAMES = 0x4F9E, 0x4FD2
    AXE_GATE = 0x4F25                     # the operand of LDA $44
    AXE_SET = {
        False: {"base": [0x18, 0x19, 0x1A, 0x1B], "frames": [0, 0, 0, 0],
                "gate": 0x44},
        True:  {"base": [0x18] * 4, "frames": [3] * 4, "gate": 0x45},
    }

    def axe_spin(self):
        base = [self.byte("f6", self.at("f6", self.AXE_BASE) + 4 + i)
                for i in range(4)]
        frames = [self.byte("f6", self.at("f6", self.AXE_FRAMES) + 4 + i)
                  for i in range(4)]
        gate = self.byte("f6", self.at("f6", self.AXE_GATE))
        now = {"base": base, "frames": frames, "gate": gate}
        state = next((k for k, v in self.AXE_SET.items() if v == now), None)
        run = [self.byte("f6", self.at("f6", 0x4FAE) + 0x18 + p)
               for p in range(4)]
        return {"on": state is True,
                "state": "on" if state is True else
                         "off" if state is False else "modified",
                "base": ["$%02X" % b for b in base],
                "frames": frames, "gate": "$%02X" % gate,
                "poses": ["$%02X" % c for c in run],
                "step": 4 if gate == 0x45 else 2,
                "at": "f6:$%04X" % self.at("f6", self.AXE_FRAMES),
                "gate_at": "f6:$%04X" % self.at("f6", self.AXE_GATE),
                "bytes": 9}

    def set_axe_spin(self, on):
        cur = self.axe_spin()
        if cur["state"] == "modified":
            raise EditError(
                "the axe's frame tables are neither the stock shape nor the "
                "repair -- refusing to overwrite them")
        want = self.AXE_SET[bool(on)]
        for i in range(4):
            self.poke("f6", self.at("f6", self.AXE_BASE) + 4 + i,
                      want["base"][i])
            self.poke("f6", self.at("f6", self.AXE_FRAMES) + 4 + i,
                      want["frames"][i])
        self.poke("f6", self.at("f6", self.AXE_GATE), want["gate"])

    # ------------------------------------ the pumpkin's missing pickup line
    # Kind 5 is the only inventory item that grants silently. The chain at
    # $527A links kinds 1, 2, 3, 4 and 9 to a message and falls through to the
    # RTS at $5298; nothing was ever written for the pumpkin. Taking the last
    # BEQ and that RTS gives three bytes for a JMP into a shim that adds the
    # missing link.
    #
    # The pointer table at $69A7 has five slots -- $24-$27 and $32 -- that no
    # code path can produce, each aimed at a neighbour's record. Slot $24 can
    # therefore be pointed at a new record without growing the table.
    HINT_TAIL = 0x5296             # BEQ L_5299 + RTS
    HINT_STOCK = bytes([0xF0, 0x01, 0x60])
    HINT_SLOT = 0x24               # a dead pointer-table slot
    HINT_SLOT_STOCK = 0x700E       # the record it idly shares with $23
    HINT_KIND = 0x05               # the plasmic pumpkin
    MSG_TABLE = 0x69A7
    MSG_SHOW = 0x687E
    HINT_P1, HINT_P2 = 0x29, 0x96  # the pickup group's framing and duration
    HINT_CODE_AT = 0x7FC4          # 12 bytes, below the water-walk shim
    HINT_REC_AT = 0x7F91           # the record, at the bottom of the tail
    HINT_MAX = 48                  # characters, so the record fits the gap
    HINT_DEFAULT = "TAKE IT TO THE PUMPKIN FIELDS|AND SET ME FREE!"
    HINT_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !?.,-^|")

    def _hint_code(self):
        """Twelve bytes. Entered with Z set from CPX #$09 and A already $3F."""
        show = self.at("f6", self.MSG_SHOW)
        return bytes([
            0xF0, 0x06,                      # BEQ show      the lantern, as before
            0xA9, self.HINT_SLOT,            # LDA #$24      the pumpkin's line
            0xE0, self.HINT_KIND,            # CPX #$05
            0xD0, 0x03,                      # BNE out
            0x4C, show & 0xFF, show >> 8,    # show: JMP sub_687E
            0x60,                            # out:  RTS
        ])

    def _hint_record(self, text):
        # The byte that terminates the text decides whether the banner shimmers.
        # sub_687E scans forward to the first byte with bit 7 set and, if it is
        # $FE, puts $FF in ram_1E7B; the display interrupt then does
        # `LDA ram_0044 / AND ram_1E7B / STA P0C2` (f6:$4121), so the frame
        # counter walks the text colour. $FF leaves the mask at zero and the
        # text sits on colour 0. Every item pickup in the stock game ends $FE.
        return bytes([self.HINT_P1, self.HINT_P2]) + text.encode("ascii") + b"\xFE"

    def _tail_runs(self, size, skip=None):
        """Every place in the free run with `size` zeroes, earliest first."""
        base, end = self.at("f6", self.FREE_BASE), self.FREE_END
        # The water-walk and extra-tick shims have fixed homes and no way to
        # move, so a record must never squat on them even while they are empty.
        taken = [(self.at("f6", self.WATER_TAIL), len(self.WATER_CODE)),
                 (self.at("f6", self.RETICK_TAIL), 16)]
        if skip is not None:
            taken.append((skip, 12))
        out, a = [], base
        while a + size <= end:
            if (all(self.byte("f6", a + i) == 0 for i in range(size))
                    and not any(a < t + n and t < a + size for t, n in taken)):
                out.append(a)
                a += size
            else:
                a += 1
        return out

    def _hint_slot_at(self):
        return self.at("f6", self.MSG_TABLE) + 2 * self.HINT_SLOT

    def pumpkin_hint(self):
        tail = self.at("f6", self.HINT_TAIL)
        here = bytes(self.slice("f6", tail, 3))
        out = {"site": "f6:$%04X" % tail, "slot": "$%02X" % self.HINT_SLOT,
               "kind": self.HINT_KIND, "max": self.HINT_MAX,
               "default": self.HINT_DEFAULT, "text": "", "at": None,
               "bytes": 0, "on": False, "state": "off"}
        if here == self.HINT_STOCK:
            return out
        if here[0] != 0x4C:
            out["state"] = "modified"
            return out
        at = here[1] | (here[2] << 8)
        rec = self.byte("f6", self._hint_slot_at()) | (
            self.byte("f6", self._hint_slot_at() + 1) << 8)
        text, i = "", rec + 2
        while len(text) <= self.HINT_MAX:
            c = self.byte("f6", i)
            if c & 0x80:
                break
            text += chr(c)
            i += 1
        ok = bytes(self.slice("f6", at, 12)) == self._hint_code()
        out.update(state="on" if ok else "modified", on=ok, text=text,
                   at="f6:$%04X" % at, record="f6:$%04X" % rec,
                   bytes=12 + len(self._hint_record(text)) + 5)
        return out

    def set_pumpkin_hint(self, on, text=None):
        tail = self.at("f6", self.HINT_TAIL)
        cur = self.pumpkin_hint()
        slot = self._hint_slot_at()
        if not on:
            if cur["at"] is None:
                return
            at = int(cur["at"].split("$")[1], 16)
            rec = int(cur["record"].split("$")[1], 16)
            self.poke("f6", at, bytes(12))
            self.poke("f6", rec, bytes(len(self._hint_record(cur["text"]))))
            stock = self.at("f6", self.HINT_SLOT_STOCK)  # what $24 shared before
            self.poke("f6", slot, bytes([stock & 0xFF, stock >> 8]))
            self.poke("f6", tail, self.HINT_STOCK)
            return
        text = (text if text is not None else
                cur["text"] or self.HINT_DEFAULT).upper()
        bad = sorted(set(text) - self.HINT_OK)
        if bad:
            raise EditError("the font has no %s -- use letters, digits, space, "
                            "! ? . , - or | for a line break"
                            % ", ".join(repr(c) for c in bad))
        if len(text) > self.HINT_MAX:
            raise EditError("%d characters, but only %d fit the free run"
                            % (len(text), self.HINT_MAX))
        for line in text.split("|"):
            if len(line) > 39:
                raise EditError("%r is %d characters; the widest line the "
                                "display fits is 39" % (line, len(line)))
        if cur["at"] is not None:            # already installed: rewrite in place
            self.set_pumpkin_hint(False)
        code, rec = self._hint_code(), self._hint_record(text)
        code_at = self._shim_place(code, self.shim_homes(len(code))
                                   + [self.at("f6", self.HINT_CODE_AT)])
        # The record is data, so it can sit anywhere free rather than at a fixed
        # home -- which lets it coexist with the test-build patcher, whose
        # routine always starts at the bottom of the run.
        runs = self._tail_runs(len(rec), skip=code_at)
        if not runs:
            fits = max([len(self._tail_runs(n, skip=code_at)) and n
                        for n in range(len(rec), 2, -1)] + [0])
            raise EditError(
                "%d characters needs %d bytes and the free run has no gap that "
                "big. %s" % (len(text), len(rec),
                             "Trim it to %d characters, or turn off another "
                             "patch." % (fits - 3) if fits > 3 else
                             "The run is full -- turn off another patch."))
        rec_at = self._shim_place(rec, runs)
        self.poke("f6", code_at, code)
        self.poke("f6", rec_at, rec)
        self.poke("f6", slot, bytes([rec_at & 0xFF, rec_at >> 8]))
        self.poke("f6", tail, bytes([0x4C, code_at & 0xFF, code_at >> 8]))

    def kind_users(self):
        """kind -> the rooms that can place it. Editing a seed hits all of them."""
        out = {}
        for r in self.rooms():
            if not self.byte("f7", self.area(r)["addr"] + 12):
                continue                       # no special-actor budget
            sk = self.screen_kind(r)
            ks = [sk["fixed"]] if sk["fixed"] is not None else sk["range"]
            for k in ks:
                out.setdefault(k, []).append(r)
        return out

    # ------------------------------------------------------- characters
    # A character is two bytes wide and sixteen lines tall, and the zone offset
    # counts DOWN: line 0 lives on the highest page and the last line on
    # CHARBASE itself. At 160x2 each byte holds four 2-bit pixels, and index 0
    # is transparent rather than a colour -- so a pixel is one of four values
    # and only three of them can be painted.
    CHAR_LINES, CHAR_PIX = 16, 8

    def char_addr(self, charbase, ch, ln, half):
        return ((charbase + (self.CHAR_LINES - 1 - ln)) << 8) | ((ch + half) & 0xFF)

    # Characters and sprites are the same thing at different sizes: MARIA forms
    # the address as (page << 8) | low, scanline n of a zone reads page+n, and
    # the offset counts DOWN. So one pair of accessors covers a terrain
    # character (2 bytes x 16 lines in an area bank) and a sprite cell (4 bytes
    # x 16 lines on f7 page $C0 or $E0) alike.
    def read_cell(self, space, page, low, width=4, lines=16):
        """`lines` rows of `width * 4` pixel values, each 0-3."""
        rows = []
        for ln in range(lines):
            base = (page + (lines - 1 - ln)) << 8
            row = []
            for bx in range(width):
                try:
                    b = self.byte(space, base | ((low + bx) & 0xFF))
                except Exception:
                    b = 0
                row += [(b >> (6 - 2 * i)) & 3 for i in range(4)]
            rows.append(row)
        return rows

    def set_cell_pixel(self, space, page, low, x, ln, value, width=4, lines=16):
        if not (0 <= ln < lines and 0 <= x < width * 4):
            raise EditError("pixel (%d, %d) is outside a %dx%d cell"
                            % (x, ln, width * 4, lines))
        if not 0 <= value <= 3:
            raise EditError("a pixel is two bits: 0 (transparent) to 3")
        bx, i = divmod(x, 4)
        addr = ((page + (lines - 1 - ln)) << 8) | ((low + bx) & 0xFF)
        b = self.byte(space, addr)
        shift = 6 - 2 * i
        self.poke(space, addr, (b & ~(3 << shift) & 0xFF) | (value << shift))

    def read_char(self, bank, charbase, ch):
        """16 rows of 8 pixel values, each 0-3."""
        return self.read_cell("b%d" % bank, charbase, ch, width=2,
                              lines=self.CHAR_LINES)

    def set_char_pixel(self, bank, charbase, ch, ln, x, value):
        self.set_cell_pixel("b%d" % bank, charbase, ch, x, ln, value,
                            width=2, lines=self.CHAR_LINES)

    def write_char(self, bank, charbase, ch, rows):
        if len(rows) != self.CHAR_LINES or any(len(r) != self.CHAR_PIX for r in rows):
            raise EditError("a character is exactly %d rows of %d pixels"
                            % (self.CHAR_LINES, self.CHAR_PIX))
        for ln, row in enumerate(rows):
            for x, v in enumerate(row):
                self.set_char_pixel(bank, charbase, ch, ln, x, v)

    def charsets(self):
        """Every (bank, charbase) actually drawn, and by which rooms."""
        out = {}
        for k in self.rooms():
            bank = self.area_bank(k)
            charbase = self.byte("f7", rooms.TBL_AREA_PAGE + self.area(k)["page"])
            out.setdefault((bank, charbase), []).append(k)
        return out

    def charset_users(self, bank, charbase):
        return self.charsets().get((bank, charbase), [])

    # ---------------------------------------------------------- palettes
    # A block is ten bands of four bytes. Byte 0 of a band is the background,
    # which MARIA takes from elsewhere here; bytes 1-3 are the three visible
    # colour indices a 2-bit pixel selects.
    # f7:$D44B, indexed by header +0. Spelled out rather than taken from
    # rooms.TBL_PAL_BLOCK because at class-body scope `rooms` is this class's
    # own method of that name, not the module.
    PAL_TBL = 0xD44B
    PAL_BANDS, PAL_STRIDE = 10, 4

    def palette_addr(self, stream):
        lo = self.byte("f7", self.PAL_TBL + stream * 2)
        hi = self.byte("f7", self.PAL_TBL + stream * 2 + 1)
        ptr = lo | (hi << 8)
        if ptr < 0xC000:
            raise EditError("stream $%02X has no palette block" % stream)
        return ptr

    def read_palette(self, stream):
        """Ten bands of three colour bytes, as stored."""
        ptr = self.palette_addr(stream)
        return [[self.byte("f7", ptr + b * self.PAL_STRIDE + c) for c in (1, 2, 3)]
                for b in range(self.PAL_BANDS)]

    def set_palette_colour(self, stream, band, index, value):
        """`index` is 1-3, matching the pixel value that selects it."""
        if not 0 <= band < self.PAL_BANDS:
            raise EditError("band %d is outside 0-%d" % (band, self.PAL_BANDS - 1))
        if not 1 <= index <= 3:
            raise EditError("colour index must be 1-3; 0 is transparent")
        ptr = self.palette_addr(stream)
        self.poke("f7", ptr + band * self.PAL_STRIDE + index, value & 0xFF)

    def palette_bands(self, stream, dark=0):
        """Ten bands of three RGB triples, as rooms.palette_block does -- but
        through this image's own palette pointer, which the European release
        moves with the rest of bank 7."""
        from palette import ntsc7800
        ptr = self.palette_addr(stream)
        out = []
        for b in range(self.PAL_BANDS):
            cols = []
            for c in (1, 2, 3):
                v = self.byte("f7", ptr + b * self.PAL_STRIDE + c)
                if dark:
                    v = (v & 0x08) >> 2
                cols.append(ntsc7800(v))
            out.append(cols)
        return out

    def palette_users(self, stream):
        return [k for k in self.rooms() if self.area(k)["stream"] == stream]

    # ---------------------------------------------------------------- items
    def item(self, kind):
        got = rooms.item_of(self, self.b7(), self.area(kind)["addr"])
        if not got:
            return None
        iid, pending, x, y = got
        return {"id": iid, "pending": pending, "x": x, "y": y}

    # The id is at header +7 -- low seven bits the item, bit 7 meaning it stays
    # pending until the room is cleared. The position is elsewhere: +22 is the
    # long axis, scaled by eight at f7:$F1C4, and +23 the cross axis in pixels.
    ITEM_ID, ITEM_X, ITEM_Y = 7, 22, 23

    # Nothing structural stops an itemless room from having one. Every header
    # carries the item fields -- the shortest is 29 bytes and they sit at +7,
    # +22 and +23 -- and the loader at f7:$F057 copies +7 straight into
    # ram_1E80 with no test on the value, so the id is the only thing that
    # makes a room itemless. 42 of the 76 rooms ship that way.
    #
    # Some of them still carry a position from wherever the data came from
    # (room $02 has $0F/$64); the rest read $00/$00, which would put the icon
    # hard against the corner, so those are given the placement rooms $0B and
    # $0C use. Either way the Item tool can drag it afterwards.
    ITEM_DEFAULT_X, ITEM_DEFAULT_Y = 0x0B, 0x64

    def add_item(self, kind, iid):
        if self.item(kind):
            raise EditError("room $%02X already has an item -- change it in "
                            "place rather than adding another, a header holds "
                            "exactly one" % kind)
        if not 1 <= int(iid) <= 0x0F:
            raise EditError("item id must be $01-$0F")
        addr = self.area(kind)["addr"]
        if not (self.byte("f7", addr + self.ITEM_X)
                or self.byte("f7", addr + self.ITEM_Y)):
            self.poke("f7", addr + self.ITEM_X, self.ITEM_DEFAULT_X)
            self.poke("f7", addr + self.ITEM_Y, self.ITEM_DEFAULT_Y)
        self.set_item(kind, iid=int(iid), pending=False)

    def remove_item(self, kind):
        """Clear the id, leaving the position bytes for if it is added back."""
        self.set_item(kind, iid=0, pending=False)

    def set_item(self, kind, iid=None, pending=None, x=None, y=None, px=True):
        """Set the room's item. `x`/`y` are pixels as `item()` reports them
        unless px=False, in which case they are written raw."""
        addr = self.area(kind)["addr"]
        if iid is not None or pending is not None:
            cur = self.byte("f7", addr + self.ITEM_ID)
            val = (cur & 0x7F) if iid is None else (iid & 0x7F)
            flag = (cur & 0x80) if pending is None else (0x80 if pending else 0)
            self.poke("f7", addr + self.ITEM_ID, val | flag)
        if x is not None:
            # invert ((raw * 8) & $7FF) - $18 - CHAR_W
            raw = ((x + 0x18 + rooms.CHAR_W) // 8) if px else x
            self.poke("f7", addr + self.ITEM_X, raw & 0xFF)
        if y is not None:
            self.poke("f7", addr + self.ITEM_Y, y & 0xFF)


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    r = RomEdit(sys.argv[1])
    ks = r.rooms()
    print("%d rooms" % len(ks))
    banks, slices = {}, {}
    for k in ks:
        a = r.area(k)
        b = r.area_bank(k)
        banks[b] = banks.get(b, 0) + 1
        for s in a["ids"]:
            slices.setdefault((b, s), 0)
            slices[(b, s)] += 1
    print("area banks in use:", ", ".join("b%d(%d rooms)" % (b, n)
                                          for b, n in sorted(banks.items())))
    print("%d distinct (bank, slice) pairs" % len(slices))
    shared = {k: v for k, v in slices.items() if v > 1}
    print("%d of them are shared by more than one segment" % len(shared))
    top = sorted(shared.items(), key=lambda kv: -kv[1])[:5]
    for (b, s), n in top:
        print("   b%d slice $%02X used %d times" % (b, s, n))
    print("no-op round trip:", "clean" if not r.dirty() else "DIRTY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
