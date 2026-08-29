#!/usr/bin/env python3
"""
Bank-aware recursive-descent 6502 disassembler for Atari 7800 SuperGame carts.

Mapping modelled (cart type 0x0012 = SuperGame + bank6@$4000):
    $4000-$7FFF  fixed  -> ROM bank 6          space "f6"
    $8000-$BFFF  banked -> ROM bank 0..7       space "b0".."b7"
    $C000-$FFFF  fixed  -> ROM bank 7 (last)   space "f7"
    any write to $8000-$FFFF sets the $8000 window bank to (data & 7)

The tracer follows control flow from the reset/NMI/IRQ vectors, carrying an
abstract value for A/X/Y (immediate constants only) so that the
`LDA #n / STA $8000` bank-switch idiom resolves automatically.  Sites where the
bank value is not a tracked constant are reported as unresolved so they can be
pinned down by hand in the annotation file.

Usage:
    python disasm.py <rom.a78> [-c annotations.json] [-o outdir]
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m6502
import a7800

BANK_SIZE = 0x4000


# ---------------------------------------------------------------- ROM/mapping
class Cart:
    def __init__(self, path):
        raw = open(path, "rb").read()
        if raw[1:10] == b"ATARI7800":
            self.header, rom = raw[:128], raw[128:]
        else:
            self.header, rom = None, raw
        self.rom = rom
        self.nbanks = len(rom) // BANK_SIZE
        self.fixed_lo = self.nbanks - 2      # bank at $4000  (bank 6 of 0..7)
        self.fixed_hi = self.nbanks - 1      # bank at $C000  (bank 7 of 0..7)

    def space_of(self, addr, bank):
        """Return the space name holding CPU `addr` given the $8000 window bank."""
        if 0x4000 <= addr < 0x8000:
            return "f6"
        if 0x8000 <= addr < 0xC000:
            return None if bank is None else "b%d" % bank
        if addr >= 0xC000:
            return "f7"
        return None                          # RAM / IO

    def base_of(self, space):
        return {"f6": 0x4000, "f7": 0xC000}.get(space, 0x8000)

    def bank_of(self, space):
        if space == "f6":
            return self.fixed_lo
        if space == "f7":
            return self.fixed_hi
        return int(space[1:])

    def byte(self, space, addr):
        off = self.bank_of(space) * BANK_SIZE + (addr - self.base_of(space))
        return self.rom[off]

    def slice(self, space, addr, n):
        off = self.bank_of(space) * BANK_SIZE + (addr - self.base_of(space))
        return self.rom[off:off + n]

    def in_space(self, space, addr):
        b = self.base_of(space)
        return b <= addr < b + BANK_SIZE


# ------------------------------------------------------------------ analysis
class Analyzer:
    def __init__(self, cart, cfg):
        self.cart = cart
        self.cfg = cfg
        self.code = set()                    # (space, addr) -> first byte of insn
        self.insn = {}                       # (space, addr) -> (mn, mode, operand, length)
        self.labels = {}                     # (space, addr) -> name
        self.kinds = {}                      # (space, addr) -> 'sub'|'code'|'data'
        self.xrefs = defaultdict(set)        # (space, addr) -> {(space, addr) of referrer}
        self.ramrefs = defaultdict(set)      # ram addr -> {referrers}
        self.bankswitch = {}                 # (space, addr) -> bank or None
        self.unresolved = []                 # sites we could not resolve
        self.forced_data = set()             # (space, addr) covered by a data block
        self.illegal_stops = set()           # traces abandoned on an illegal opcode
        self._pending = []

    # -- helpers -------------------------------------------------------------
    def mark(self, loc, kind):
        if self.kinds.get(loc) != "sub":
            self.kinds[loc] = kind

    def add_entry(self, space, addr, bank, kind="code", src=None):
        if space is None:
            if src:
                self.unresolved.append((src, addr))
            return
        if not self.cart.in_space(space, addr):
            return
        self.mark((space, addr), kind)
        if src:
            self.xrefs[(space, addr)].add(src)
        self._pending.append((space, addr, bank))

    # -- the trace -----------------------------------------------------------
    def run(self, entries):
        for space, addr, bank in entries:
            self.add_entry(space, addr, bank, "sub")
        seen = set()
        while self._pending:
            space, addr, bank = self._pending.pop()
            a = x = y = None
            while True:
                key = (space, addr, bank, a)
                if key in seen:
                    break
                seen.add(key)
                loc = (space, addr)
                if loc in self.forced_data or not self.cart.in_space(space, addr):
                    break
                # manual override: assert which bank is really in the $8000
                # window here, for paths the constant-tracker cannot follow
                pinned = self.cfg.bankat.get(fmt_loc(loc))
                if pinned is not None:
                    bank = pinned

                op = self.cart.byte(space, addr)
                mn, mode, illegal = m6502.OPCODES[op]
                # An undocumented opcode in a traced path means the path is not
                # code. This cartridge uses none in anything confirmed, so a
                # branch that lands on one is a static edge the machine never
                # takes -- b0:$BDEC branches into a text block that way. Walking
                # on emits instructions the assembler cannot reproduce, which
                # breaks the round trip.
                if illegal:
                    self.illegal_stops.add(loc)
                    break
                n = m6502.MODES[mode]
                if not self.cart.in_space(space, addr + n):
                    break
                operand = None
                if n == 1:
                    operand = self.cart.byte(space, addr + 1)
                elif n == 2:
                    operand = (self.cart.byte(space, addr + 1)
                               | (self.cart.byte(space, addr + 2) << 8))

                self.code.add(loc)
                self.insn[loc] = (mn, mode, operand, 1 + n)
                if loc not in self.kinds:
                    self.kinds[loc] = "code"

                nxt = addr + 1 + n

                # --- abstract A/X/Y (immediates only) ---
                if mn == "LDA":
                    a = operand if mode == "imm" else None
                elif mn == "LDX":
                    x = operand if mode == "imm" else None
                elif mn == "LDY":
                    y = operand if mode == "imm" else None
                elif mn == "TAX":
                    x = a
                elif mn == "TAY":
                    y = a
                elif mn == "TXA":
                    a = x
                elif mn == "TYA":
                    a = y
                elif mn in ("PLA",):
                    a = None
                elif mn in ("ADC", "SBC", "AND", "ORA", "EOR", "ASL", "LSR",
                            "ROL", "ROR", "LAX", "LDA"):
                    a = None
                elif mn in ("INX", "DEX"):
                    x = None if x is None else (x + (1 if mn == "INX" else -1)) & 0xFF
                elif mn in ("INY", "DEY"):
                    y = None if y is None else (y + (1 if mn == "INY" else -1)) & 0xFF

                # --- bank switching: any store into $8000-$FFFF ---
                if mn in m6502.STORES and mode in ("abs", "abx", "aby") \
                        and operand is not None and operand >= 0x8000:
                    src = {"STA": a, "STX": x, "STY": y}.get(mn)
                    forced = self.cfg.banksw.get(fmt_loc(loc))
                    if isinstance(forced, list):
                        # bank number came from a table; fork the trace so every
                        # bank the table can select gets explored
                        self.bankswitch[loc] = forced
                        for b in forced[1:]:
                            self._pending.append((space, nxt, b))
                        bank = forced[0]
                    elif forced == "keep":
                        # e.g. `LDA cur_bank / STA $8000` -- restores whatever
                        # bank was already selected, so the tracer's idea of the
                        # current bank stays valid.
                        self.bankswitch[loc] = "keep"
                    else:
                        val = forced if forced is not None else src
                        self.bankswitch[loc] = None if val is None else (val & 7)
                        if val is None:
                            self.unresolved.append((loc, None))
                            bank = None
                        else:
                            bank = val & 7

                # --- references ---
                elif mode in ("abs", "abx", "aby", "ind", "zp", "zpx", "zpy",
                              "izx", "izy") and operand is not None:
                    tgt = operand
                    if tgt >= 0x4000:
                        tspace = self.cart.space_of(tgt, bank)
                        if tspace:
                            self.xrefs[(tspace, tgt)].add(loc)
                            if (tspace, tgt) not in self.kinds:
                                self.kinds[(tspace, tgt)] = "data"
                    else:
                        self.ramrefs[tgt].add(loc)

                # --- control flow ---
                if mn == "JSR":
                    tspace = self.cart.space_of(operand, bank)
                    self.add_entry(tspace, operand, bank, "sub", loc)
                elif mn == "JMP" and mode == "abs":
                    tspace = self.cart.space_of(operand, bank)
                    self.add_entry(tspace, operand, bank, "sub", loc)
                    break
                elif mn == "JMP" and mode == "ind":
                    break
                elif mn in m6502.BRANCHES:
                    tgt = (nxt + ((operand ^ 0x80) - 0x80)) & 0xFFFF
                    tspace = self.cart.space_of(tgt, bank)
                    self.add_entry(tspace, tgt, bank, "code", loc)
                elif mn in ("RTS", "RTI", "BRK", "JAM"):
                    break

                addr = nxt

    def scan_ram_vectors(self, lo_addr, hi_addr, window=24):
        """Find `LDA #lo / STA nmi_vec_lo` + `LDA #hi / STA nmi_vec_hi` pairs.

        MARIA's NMI goes through `JMP (nmi_vec)`, and each DLI installs the
        handler for the next zone, so the whole DLI chain is only reachable by
        following these stores.  Returns a list of (space, addr) handlers.
        """
        found = []
        spaces = sorted({s for (s, a) in self.code})
        for space in spaces:
            addrs = sorted(a for (s, a) in self.code if s == space)
            los, his = [], []
            last_imm = None
            for a in addrs:
                mn, mode, operand, length = self.insn[(space, a)]
                if mn == "LDA" and mode == "imm":
                    last_imm = operand
                elif mn == "STA" and mode in ("abs", "zp"):
                    if operand == lo_addr and last_imm is not None:
                        los.append((a, last_imm))
                    elif operand == hi_addr and last_imm is not None:
                        his.append((a, last_imm))
                elif mn in ("LDA", "PLA", "TXA", "TYA"):
                    last_imm = None
            for la, lv in los:
                for ha, hv in his:
                    if abs(ha - la) <= window:
                        found.append((lv | (hv << 8), (space, la)))
        return found

    # -- naming --------------------------------------------------------------
    def name_all(self):
        for loc in sorted(set(self.kinds) | set(self.labels)):
            if fmt_loc(loc) in self.cfg.labels:
                self.labels[loc] = self.cfg.labels[fmt_loc(loc)]
                continue
            if loc in self.labels:
                continue
            # only name something that is actually referenced, or is a
            # subroutine entry -- otherwise every instruction gets a label
            if not self.xrefs.get(loc) and self.kinds.get(loc) != "sub":
                continue
            space, addr = loc
            tag = "" if space in ("f6", "f7") else space[1:]
            kind = self.kinds.get(loc, "code")
            if kind == "sub" and loc in self.code:
                self.labels[loc] = "sub%s_%04X" % (tag, addr)
            elif kind == "data" or loc not in self.code:
                self.labels[loc] = "dat%s_%04X" % (tag, addr)
            else:
                self.labels[loc] = "L%s_%04X" % (tag, addr)


def fmt_loc(loc):
    return "%s:%04X" % (loc[0], loc[1])


def parse_loc(s):
    space, addr = s.split(":")
    return (space, int(addr, 16))


# -------------------------------------------------------------------- config
class Config:
    def __init__(self, path=None):
        d = {}
        if path and os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
        self.entries = [parse_loc(s) for s in d.get("entries", [])]
        self.labels = d.get("labels", {})
        self.comments = d.get("comments", {})
        self.headers = d.get("headers", {})       # block comment printed above a line
        self.ram = {int(k, 16): v for k, v in d.get("ram", {}).items()}
        self.banksw = {k: v for k, v in d.get("banksw", {}).items()}
        self.blocks = d.get("blocks", [])
        self.bankat = d.get("bankat", {})
        self.notes = d.get("notes", {})


# ------------------------------------------------------------------- emitter
# (mnemonic, mode) pairs that exist as documented opcodes
MODESET = {(mn, md) for (mn, md, il) in m6502.OPCODES.values() if not il}
ZP_OF = {"abs": "zp", "abx": "zpx", "aby": "zpy"}


class Emitter:
    def __init__(self, cart, an, cfg):
        self.cart, self.an, self.cfg = cart, an, cfg
        self.used = defaultdict(dict)     # space -> {symbol name: address}
        self.emitted = defaultdict(set)   # space -> {label names actually written}

    def opnd_text(self, loc, mn, mode, operand, length):
        if mode in ("imp", "acc"):
            return m6502.FMT[mode]
        space, addr = loc
        if mode == "imm":
            return "#$%02X" % operand
        if loc in self.an.bankswitch:
            # a store into $8000-$FFFF is the SuperGame bank register, not a
            # reference to whatever code/data happens to live at that address
            return m6502.FMT[mode].format(v="$%04X" % operand)
        if mode == "rel":
            tgt = (addr + length + ((operand ^ 0x80) - 0x80)) & 0xFFFF
            return self.ref_name(loc, tgt)
        # memory operand
        v = self.ref_name(loc, operand, zp=(mode in ("zp", "zpx", "zpy", "izx", "izy")))
        return m6502.FMT[mode].format(v=v)

    def note(self, space, name, addr):
        self.used[space][name] = addr
        return name

    def ref_name(self, src, tgt, zp=False):
        # hardware register?
        hw = a7800.HW.get(tgt)
        if hw and tgt < 0x0400:
            return self.note(src[0], hw, tgt)
        if tgt in self.cfg.ram:
            return self.note(src[0], self.cfg.ram[tgt], tgt)
        if tgt < 0x4000:
            if tgt < 0x0040:
                return "$%02X" % tgt
            return self.note(src[0], "ram_%04X" % tgt, tgt)
        # cart address: label if we have one in the same space (or fixed space)
        for space in self.spaces_for(src[0], tgt):
            if (space, tgt) in self.an.labels:
                return self.note(src[0], self.an.labels[(space, tgt)], tgt)
        return "$%02X" % tgt if zp else "$%04X" % tgt

    def spaces_for(self, cur_space, tgt):
        if 0x4000 <= tgt < 0x8000:
            return ["f6"]
        if tgt >= 0xC000:
            return ["f7"]
        if 0x8000 <= tgt < 0xC000:
            return [cur_space] if cur_space.startswith("b") else \
                   ["b%d" % i for i in range(self.cart.nbanks)]
        return []

    def emit_space(self, space, out):
        cart, an, cfg = self.cart, self.an, self.cfg
        base = cart.base_of(space)
        bank = cart.bank_of(space)
        w = []
        role = {"f6": "fixed at $4000-$7FFF", "f7": "fixed at $C000-$FFFF"}.get(
            space, "swapped into the $8000-$BFFF window")
        ncode = sum(1 for (s, a) in an.code if s == space)
        w.append("; " + "=" * 76)
        # take the name from the cartridge's own a78 header rather than a
        # constant, so a PAL image is not labelled as the NTSC one
        title = "Midnight Mutants"
        if cart.header:
            t = bytes(cart.header[17:49]).rstrip(chr(0).encode()).decode("latin-1").strip()
            if t:
                title = t
        w.append("; %s -- ROM bank %d" % (title, bank))
        w.append(";   space '%s': %s" % (space, role))
        w.append(";   file offset $%05X-$%05X (a78 header included)"
                 % (128 + bank * BANK_SIZE, 128 + (bank + 1) * BANK_SIZE - 1))
        w.append(";   %d instructions reached by the tracer" % ncode)
        if space in cfg.notes:
            for line in cfg.notes[space].splitlines():
                w.append(";   " + line)
        w.append("; " + "=" * 76)
        w.append("")
        equ_at = len(w)                   # equates get spliced in here at the end
        w.append("    .org $%04X" % base)
        w.append("")

        blocks = {}
        for b in cfg.blocks:
            s, a = parse_loc(b["loc"])
            if s == space:
                blocks[a] = b

        addr = base
        end = base + BANK_SIZE
        data_run = []

        def flush():
            if not data_run:
                return
            start = data_run[0][0]
            byts = bytes(x[1] for x in data_run)
            self.emit_bytes(w, space, start, byts)
            data_run.clear()

        while addr < end:
            loc = (space, addr)
            blk = blocks.get(addr)
            if blk:
                flush()
                addr = self.emit_block(w, space, addr, blk)
                continue
            if loc in an.code:
                flush()
                self.emit_insn(w, space, addr)
                addr += an.insn[loc][3]
            else:
                if loc in an.labels or loc in cfg.headers or len(data_run) >= 4096:
                    flush()
                data_run.append((addr, cart.byte(space, addr)))
                addr += 1
        flush()

        # Everything referenced by name but not *defined* in this file needs an
        # equate: hardware registers, RAM, labels in the other banks, and labels
        # that landed inside a data block (e.g. the high half of a word table,
        # which code addresses as its own base) so were never written out.
        defined = self.emitted[space]
        ext = {n: v for n, v in self.used[space].items() if n not in defined}
        equ = ["; ---- equates: hardware, RAM and cross-bank labels ----"]
        for n, v in sorted(ext.items(), key=lambda kv: (kv[1], kv[0])):
            equ.append("%-16s = $%04X" % (n, v))
        equ += ["", ""]
        w[equ_at:equ_at] = equ

        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(w) + "\n")

    def emit_label(self, w, space, addr):
        loc = (space, addr)
        an, cfg = self.an, self.cfg
        key = fmt_loc(loc)
        if key in cfg.headers:
            w.append("")
            for line in cfg.headers[key].splitlines():
                w.append("; " + line)
        if loc in an.labels:
            refs = sorted(an.xrefs.get(loc, ()))
            if refs:
                names = ", ".join(
                    "%s" % (an.labels.get(r) or fmt_loc(r)) for r in refs[:8])
                if len(refs) > 8:
                    names += ", +%d more" % (len(refs) - 8)
                w.append("; xrefs: " + names)
            w.append("%s:" % an.labels[loc])
            self.emitted[space].add(an.labels[loc])

    def emit_insn(self, w, space, addr):
        an, cfg = self.an, self.cfg
        loc = (space, addr)
        self.emit_label(w, space, addr)
        mn, mode, operand, length = an.insn[loc]
        raw = self.cart.slice(space, addr, length)
        txt = self.opnd_text(loc, mn, mode, operand, length)
        illegal = m6502.OPCODES[raw[0]][2]
        # `LDX $00FF,Y` could reassemble as zero-page,Y; force the absolute form
        force = (mode in ZP_OF and operand is not None and operand < 0x100
                 and (mn, ZP_OF[mode]) in MODESET)
        line = "    %-9s %s" % (mn + ("*" if illegal else ".w" if force else ""), txt)
        comment = cfg.comments.get(fmt_loc(loc), "")
        if loc in an.bankswitch:
            b = an.bankswitch[loc]
            auto = "bank switch -> " + (
                "restores the shadowed bank" if b == "keep" else
                "bank %s (from a table)" % "/".join(map(str, b))
                if isinstance(b, list) else
                "bank %d" % b if b is not None else
                "UNRESOLVED (value not a constant)")
            comment = (comment + "  " if comment else "") + auto
        w.append("%-44s ; %04X: %-8s %s"
                 % (line, addr, raw.hex(" ").upper(), comment))

    def emit_bytes(self, w, space, start, byts):
        self.emit_label(w, space, start)
        for i in range(0, len(byts), 16):
            chunk = byts[i:i + 16]
            hexs = ",".join("$%02X" % b for b in chunk)
            ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            w.append("    .byte %-64s ; %04X  %s" % (hexs, start + i, ascii_))

    def emit_block(self, w, space, addr, blk):
        cart, an = self.cart, self.an
        end = parse_loc(blk["end"])[1] if "end" in blk else addr + blk.get("len", 1)
        if blk.get("name"):
            an.labels[(space, addr)] = blk["name"]
        self.emit_label(w, space, addr)
        typ = blk.get("type", "bytes")
        data = cart.slice(space, addr, end - addr)
        if typ == "words":
            for i in range(0, len(data) - 1, 2):
                v = data[i] | (data[i + 1] << 8)
                nm = self.ref_name((space, addr + i), v)
                w.append("    .word %-20s ; %04X: %02X %02X"
                         % (nm, addr + i, data[i], data[i + 1]))
        else:
            # a label can land inside a data block (something references the
            # middle of a table); break the block so the label still gets a
            # definition, otherwise the listing will not reassemble
            cuts = sorted(a for a in range(addr + 1, end)
                          if (space, a) in an.labels
                          or fmt_loc((space, a)) in self.cfg.headers)
            for lo, hi in zip([addr] + cuts, cuts + [end]):
                self.emit_bytes(w, space, lo, cart.slice(space, lo, hi - lo))
        return end


def check_gaps(an, cart, spaces):
    """Are the unreached byte ranges really free of missed code?

    A gap is a range the recursive descent never entered, and the obvious
    check is to scan for a JSR/JMP whose operand lands in one. That scan is
    close to pure noise on its own: $20/$4C/$6C are ordinary byte values that
    occur constantly inside graphics and tables and as the second or third
    byte of longer instructions, so the coincidences outnumber the real call
    sites heavily.

    Two things make it trustworthy, and the second matters here in particular:

      * The tracer already knows every address that is the FIRST byte of an
        instruction. A candidate whose opcode byte is not one of those is not
        an instruction at all.
      * For `JMP ($xxxx)` the operand is the POINTER, not the target, so it
        is dereferenced. This game's display-interrupt chain runs on RAM
        vectors -- each DLI installs the handler for the next zone -- and a
        scan that compares the operand against the gap list is asking about
        the wrong address every time.

    Prints one line per candidate, classified, so "no missed code" is a
    checked claim rather than an asserted one.
    """
    real, bogus, ramind = [], [], []
    for space in spaces:
        base = cart.base_of(space)
        size = BANK_SIZE
        in_rom = lambda x: cart.in_space(space, x)
        covered = set()
        for (sp, a) in an.code:
            if sp != space:
                continue
            for i in range(an.insn[(sp, a)][3]):
                covered.add(a + i)
        for (sp, a) in an.forced_data:
            if sp == space:
                covered.add(a)
        for a in range(base, base + size - 2):
            try:
                op = cart.byte(space, a)
            except Exception:                                # noqa: BLE001
                continue
            if op not in (0x20, 0x4C, 0x6C):
                continue
            operand = cart.byte(space, a + 1) | (cart.byte(space, a + 2) << 8)
            traced = (space, a) in an.code
            if op == 0x6C:
                if not in_rom(operand):
                    if traced:
                        ramind.append((space, a, operand))
                    continue
                target = (cart.byte(space, operand)
                          | (cart.byte(space, operand + 1) << 8))
                name = "JMP ($%04X) ->" % operand
            else:
                target = operand
                name = "JSR" if op == 0x20 else "JMP"
            if not in_rom(target) or target in covered:
                continue
            (real if traced else bogus).append((space, a, target, name))

    print("\ngap entry points (apparent JSR/JMP into an unreached range):")
    if not (real or bogus or ramind):
        print("  none")
        return 0
    if bogus:
        print("  %d coincidence%s -- the opcode byte is not an instruction "
              "start, so it is data or a mid-instruction byte:"
              % (len(bogus), "" if len(bogus) == 1 else "s"))
        for space, a, t, nm in bogus[:12]:
            print("    %s:%04X  %-16s $%04X" % (space, a, nm, t))
        if len(bogus) > 12:
            print("    ... and %d more" % (len(bogus) - 12))
    if real:
        print("  %d REAL call site%s -- a traced instruction branching into an "
              "unreached range. Investigate:"
              % (len(real), "" if len(real) == 1 else "s"))
        for space, a, t, nm in real:
            print("    %s:%04X  %-16s $%04X   <-- MISSED CODE" % (space, a, nm, t))
    elif bogus:
        print("  no real call site among them.")
    if ramind:
        print("  %d traced JMP ($xxxx) through a RAM pointer -- target not "
              "knowable statically (this is the DLI chain):" % len(ramind))
        for space, a, ptr in ramind[:8]:
            print("    %s:%04X  JMP ($%04X)" % (space, a, ptr))
        if len(ramind) > 8:
            print("    ... and %d more" % (len(ramind) - 8))
    return len(real)


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-c", "--config", default=None)
    ap.add_argument("-o", "--outdir", default="src")
    ap.add_argument("--check-gaps", action="store_true",
                    help="for every apparent JSR/JMP into a range the tracer "
                         "never reached, say whether it is a real instruction "
                         "or just the opcode byte occurring inside data")
    args = ap.parse_args()

    cart = Cart(args.rom)
    cfg = Config(args.config)
    an = Analyzer(cart, cfg)

    for b in cfg.blocks:
        s, a = parse_loc(b["loc"])
        e = parse_loc(b["end"])[1] if "end" in b else a + b.get("len", 1)
        for x in range(a, e):
            an.forced_data.add((s, x))

    # vectors live in the fixed high bank
    last = cart.rom[cart.fixed_hi * BANK_SIZE:]
    nmi = last[0x3FFA] | (last[0x3FFB] << 8)
    res = last[0x3FFC] | (last[0x3FFD] << 8)
    irq = last[0x3FFE] | (last[0x3FFF] << 8)

    entries = []
    for name, v in (("RESET", res), ("NMI", nmi), ("IRQ", irq)):
        sp = cart.space_of(v, None)
        if sp:
            entries.append((sp, v, None))
            an.labels[(sp, v)] = name + "_" + ("%04X" % v)
    entries += [(s, a, None) for (s, a) in cfg.entries]

    an.run(entries)

    # The DLI chain is only reachable through the RAM vector MARIA jumps
    # through, so keep re-tracing until no new handler addresses turn up.
    dli = {}
    for _ in range(8):
        new = []
        for tgt, site in an.scan_ram_vectors(0x2135, 0x2136):
            sp = cart.space_of(tgt, None)
            if sp and (sp, tgt) not in dli:
                dli[(sp, tgt)] = site
                new.append((sp, tgt, None))
        if not new:
            break
        for sp, tgt, _b in new:
            an.mark((sp, tgt), "sub")
        an.run(new)
    for i, loc in enumerate(sorted(dli)):
        an.labels.setdefault(loc, "DLI_%04X" % loc[1])

    an.name_all()
    for name, v in (("NMI", nmi), ("RESET", res), ("IRQ", irq)):
        sp = cart.space_of(v, None)
        if sp:
            an.labels[(sp, v)] = cfg.labels.get(fmt_loc((sp, v)), name + "_HANDLER")

    os.makedirs(args.outdir, exist_ok=True)
    em = Emitter(cart, an, cfg)
    spaces = ["f6", "f7"] + ["b%d" % i for i in range(cart.nbanks)]
    for space in spaces:
        n = sum(1 for (s, a) in an.code if s == space)
        if space.startswith("b") and n == 0 and space not in cfg.notes:
            continue
        em.emit_space(space, os.path.join(args.outdir, "%s.asm" % space))

    # ---- report ----
    print("vectors: NMI=$%04X RESET=$%04X IRQ=$%04X" % (nmi, res, irq))
    print("\ncoverage (bytes reached as code, per 16K space):")
    tot = 0
    for space in spaces:
        cnt = sum(an.insn[(s, a)][3] for (s, a) in an.code if s == space)
        tot += cnt if space.startswith(("f",)) or cnt else 0
        if cnt:
            print("  %-4s bank %d  %6d/%d bytes  %5.1f%%   (%d instructions)"
                  % (space, cart.bank_of(space), cnt, BANK_SIZE,
                     100.0 * cnt / BANK_SIZE,
                     sum(1 for (s, a) in an.code if s == space)))
    if args.check_gaps:
        check_gaps(an, cart, [sp for sp in spaces
                              if any(x == sp for (x, _a) in an.code)])

    if an.bankswitch:
        print("\nbank-switch sites:")
        for loc in sorted(an.bankswitch):
            b = an.bankswitch[loc]
            print("  %-10s -> %s" % (
                fmt_loc(loc),
                "restores shadow" if b == "keep" else
                "banks %s (table)" % "/".join(map(str, b)) if isinstance(b, list) else
                "bank %d" % b if b is not None else "UNRESOLVED"))
    print("\nmost-referenced RAM addresses:")
    for a_, refs in sorted(an.ramrefs.items(), key=lambda kv: -len(kv[1]))[:40]:
        nm = cfg.ram.get(a_) or a7800.HW.get(a_) or ""
        print("  $%04X  %3d refs  %s" % (a_, len(refs), nm))


if __name__ == "__main__":
    main()
