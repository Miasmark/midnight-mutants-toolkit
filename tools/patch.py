#!/usr/bin/env python3
"""
Build a test build of the cartridge that starts with chosen inventory and
progression flags already set, so an experiment does not need a play-through
to reach its starting conditions.

How it works, cheapest first.

**Some values need no code at all.**  Starting health and blood purity are
already written by immediates the reset executes -- LDA #$27 at f6:$4AE4 into
hp_cur and hp_max, LDA #$64 at f6:$4AE0 into blood_purity -- so --hp and
--purity just change those operands.  A build asking only for those installs no
hook and appends nothing: two bytes differ from the stock cartridge.

**The rest needs a routine**, because inventory slots and boss_flags want
individual stores.  It is appended in the free run at f6:$7F91 and reached by
displacing one instruction on the reset path.  That instruction is the lone
"STA $1FD9" at f6:$4AC8 -- three bytes, which the routine re-does first.  An
earlier version hooked the 14-byte clear sequence at $4AE9 and had to repeat
all of it, spending eleven more bytes of the free run on saying nothing.

Sizes: 3 for the displaced store, 5 per item, 5 for boss flags, 4 per
zero-page value, 1 for the RTS.  So an axe, a lantern and a boss flag come to
19 bytes, and every item at once to 74.

Nothing else moves, so the patch cannot disturb bank layout or timing outside
that routine, and both cartridge layouts are handled -- the addresses above are
the NTSC ones and the European image shifts them by three.

Usage:
  python patch.py <rom.a78> -o out.a78 --item 0D=1 --item 09=1 --boss-flags 01
  python patch.py <rom.a78> -o out.a78 --hp 4F --purity 64
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart, BANK_SIZE
from reloc import relocate, detect

# Both addresses below are the NTSC ones. The European cartridge shifts bank 6
# by three bytes from $42B7 onward, which moves the hook and the start of the
# free run alike -- $7F91 holds code there, and the run begins at $7F94.
# The hook displaces one instruction and the routine re-does it, so the shorter
# the instruction the less of the free run is spent on saying nothing. $4AC8 is
# a lone "STA $1FD9" on the straight-line reset path, three bytes against the
# fourteen of the clear sequence that used to be displaced.
HOOK = 0x4AC8
HOOK_LEN = 3
ORIGINAL = bytes.fromhex("8DD91F")          # STA $1FD9
FREE = 0x7F91          # the free run at the end of bank 6

# Two starting values are already written by immediates the reset executes, so
# they need no appended code at all -- just a different operand.
HP_IMM = 0x4AE4        # LDA #$27 -> hp_cur and hp_max
PURITY_IMM = 0x4AE0    # LDA #$64 -> blood_purity

INVENTORY = 0x1F3D     # item n lives at INVENTORY + n
BOSS_FLAGS = 0x1FBC
HP_CUR = 0xC5
HP_MAX = 0xC6

# The special-actor contact handler loads a fixed damage of $10 (16) before
# calling DamageHealth.  That cast is the ghosts, the throwing cave zombies and
# the pumpkin-headed throwers -- 16 is by far the largest contact hit in the
# game, and it is what makes the caves punishing to survey.  Only the immediate
# operand moves; the instruction and everything around it stay put.
SACTOR_DMG = 0x6718        # operand of LDA #$10 at f6:$6717
SACTOR_DMG_DEFAULT = 0x10

# Boss contact damage, bank 5, indexed by mode_flag: [unused, skull, ram, evil]
# = $60 $0A $05 $09.  b5:$BBD2 does LDA L5_BBFD,Y with Y = mode_flag before
# calling DamageHealth, so these are the per-boss contact hits (halved by the
# cross, like every other health source).
BOSS_DMG = 0xBBFD
BOSS_DMG_DEFAULT = bytes([0x60, 0x0A, 0x05, 0x09])
BOSS_NAME = {1: "skull", 2: "ram", 3: "evil"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--item", action="append", default=[],
                    metavar="HH=N", help="inventory slot in hex = count, repeatable")
    ap.add_argument("--zp", action="append", default=[], metavar="HH=N",
                    help="zero-page address in hex = value, repeatable")
    ap.add_argument("--kit", action="store_true",
                    help="standard test kit: cross ($01) and one of each potion ($06, $07)")
    ap.add_argument("--boss-flags", default=None, metavar="HH")
    ap.add_argument("--hp", default=None, metavar="HH",
                    help="starting hp_max and hp_cur in hex ($4F is the in-game max)")
    ap.add_argument("--purity", default=None, metavar="HH",
                    help="starting blood purity; costs no space, it is the "
                         "operand of an immediate the reset already runs")
    ap.add_argument("--sactor-damage", default=None, metavar="HH",
                    help="replace the special-actor contact damage (default $10) "
                         "-- the humpback/ghost/thrower cast at f6:$6717")
    ap.add_argument("--boss-damage", action="append", default=[],
                    metavar="NAME=HH",
                    help="boss contact damage, e.g. evil=03 (skull|ram|evil)")
    ap.add_argument("--explore", action="store_true",
                    help="cave-exploration kit: cross, heart, lantern, mega "
                         "blaster, full health, special-actor damage $02")
    args = ap.parse_args()

    if args.explore:
        args.item = ["01=1", "04=1", "09=1"] + args.item     # cross, heart, lantern
        # --zp values parse base-0, so the rate goes in as 0x0A, matching how
        # the existing mm-megablaster build sets it
        args.zp = ["86=3", "88=0x0A"] + args.zp              # mega blaster + its rate
        if args.hp is None:
            args.hp = "4F"
        if args.sactor_damage is None:
            args.sactor_damage = "02"

    if args.kit:                       # cross halves all health damage; one of
        args.item = ["01=1", "06=1", "07=1"] + args.item   # each potion, un-stacked
    cart = Cart(args.rom)
    version = detect(cart)
    if version is None:
        print("this cartridge matches neither the NTSC nor the European "
              "layout; refusing to patch it blind")
        return 1
    hook = relocate(version, "f6", HOOK)
    free = relocate(version, "f6", FREE)
    hp_imm = relocate(version, "f6", HP_IMM)
    purity_imm = relocate(version, "f6", PURITY_IMM)
    raw = bytearray(open(args.rom, "rb").read())
    hdr = 128 if cart.header else 0
    b6 = cart.fixed_lo * BANK_SIZE + hdr

    def off(addr):                     # bank-6 CPU address -> file offset
        return b6 + (addr - 0x4000)

    if bytes(raw[off(hook):off(hook) + HOOK_LEN]) != ORIGINAL:
        print("refusing to patch: the bytes at $%04X are not the instruction "
              "this hooks" % hook)
        return 1

    # --- build the replacement routine ---
    code = bytearray(ORIGINAL)         # do exactly what we displaced, first
    for spec in args.item:
        slot, _, cnt = spec.partition("=")
        s, n = int(slot, 16), int(cnt or "1")
        addr = INVENTORY + s
        code += bytes([0xA9, n, 0x8D, addr & 0xFF, addr >> 8])   # LDA #n : STA addr
    for spec in args.zp:
        slot, _, val = spec.partition("=")
        code += bytes([0xA9, int(val, 0) & 0xFF, 0x85, int(slot, 16)])  # LDA #v : STA zp
    if args.boss_flags is not None:
        v = int(args.boss_flags, 16)
        code += bytes([0xA9, v, 0x8D, BOSS_FLAGS & 0xFF, BOSS_FLAGS >> 8])
    code += bytes([0x60])              # RTS

    # Starting health and purity are written by immediates the reset already
    # runs, so they cost nothing here: change the operand and the existing code
    # does the work.
    immediates = []
    if args.hp is not None:
        immediates.append((hp_imm, int(args.hp, 16), "starting health"))
    if args.purity is not None:
        immediates.append((purity_imm, int(args.purity, 16), "starting purity"))

    # Measure the run that is actually free rather than assuming the tail is.
    # tools/editor.py can install its own shims there -- water walk at $7FD0
    # and the music retick at $7FF0 -- so an image that has been through the
    # editor may have far less room than a stock one.
    avail = 0
    while free + avail < 0x8000 and raw[off(free + avail)] == 0:
        avail += 1
    if len(code) > avail:
        print("patch routine is %d bytes and only %d are free at $%04X"
              % (len(code), avail, free))
        if free + avail < 0x8000:
            print("  $%04X holds something already -- an editor patch, most "
                  "likely. Turn it off, or build the test cart first and patch "
                  "it in the editor afterwards." % (free + avail))
        return 1
    if any(raw[off(free) + i] for i in range(len(code))):
        print("refusing to patch: $%04X-$%04X is not empty"
              % (free, free + len(code) - 1))
        return 1

    # If the only things asked for are the two immediates, there is nothing to
    # append and the hook is not installed at all -- the reset runs unchanged
    # apart from two operands.
    needs_routine = len(code) > len(ORIGINAL) + 1      # more than prefix + RTS
    if needs_routine:
        raw[off(free):off(free) + len(code)] = code
        # JSR to it, then pad the rest of the displaced run with NOPs
        raw[off(hook):off(hook) + HOOK_LEN] = \
            bytes([0x20, free & 0xFF, free >> 8]) + bytes([0xEA]) * (HOOK_LEN - 3)
    for addr, val, _ in immediates:
        raw[off(addr)] = val & 0xFF

    if args.boss_damage:
        b5 = 5 * BANK_SIZE + hdr           # bank 5 image start
        base = b5 + (BOSS_DMG - 0x8000)
        if bytes(raw[base:base + 4]) != BOSS_DMG_DEFAULT:
            print("refusing to patch: boss damage table at b5:$%04X is not the "
                  "expected %s" % (BOSS_DMG, BOSS_DMG_DEFAULT.hex()))
            return 1
        want = {v: k for k, v in BOSS_NAME.items()}
        for spec in args.boss_damage:
            name, _, val = spec.partition("=")
            if name not in want:
                print("unknown boss %r -- use skull, ram or evil" % name)
                return 1
            raw[base + want[name]] = int(val, 16)

    if args.sactor_damage is not None:
        if raw[off(SACTOR_DMG)] != SACTOR_DMG_DEFAULT:
            print("refusing to patch: byte at $%04X is $%02X, not the expected "
                  "$%02X" % (SACTOR_DMG, raw[off(SACTOR_DMG)], SACTOR_DMG_DEFAULT))
            return 1
        raw[off(SACTOR_DMG)] = int(args.sactor_damage, 16)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    open(args.out, "wb").write(bytes(raw))
    print("wrote %s (%d bytes)" % (args.out, len(raw)))
    if needs_routine:
        print("  hook   $%04X -> JSR $%04X" % (hook, free))
    else:
        print("  no routine needed -- nothing had to be appended")
    for addr, val, what in immediates:
        print("  $%04X  = $%02X   %s, in place" % (addr, val, what))
    if needs_routine:
        print("  routine $%04X, %d bytes  (%s layout)" % (free, len(code), version))
    for spec in args.item:
        slot, _, cnt = spec.partition("=")
        print("  item $%02X = %s  (at $%04X)"
              % (int(slot, 16), cnt or "1", INVENTORY + int(slot, 16)))
    for spec in args.zp:
        slot, _, val = spec.partition("=")
        print("  zp $%02X = %s" % (int(slot, 16), val))
    if args.boss_flags is not None:
        print("  boss_flags = $%s" % args.boss_flags.upper())
    if args.hp is not None:
        print("  hp_max = hp_cur = $%s" % args.hp.upper())
    for spec in args.boss_damage:
        name, _, val = spec.partition("=")
        print("  %s boss contact damage $%02X -> $%s"
              % (name, BOSS_DMG_DEFAULT[{v: k for k, v in BOSS_NAME.items()}[name]],
                 val.upper()))
    if args.sactor_damage is not None:
        print("  special-actor contact damage $%02X -> $%s  (f6:$%04X)"
              % (SACTOR_DMG_DEFAULT, args.sactor_damage.upper(), SACTOR_DMG - 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
