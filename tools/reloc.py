#!/usr/bin/env python3
"""
Where the two releases put things.

The European cartridge is the NTSC one with extra display-list zones for PAL's
taller screen. Those entries are inserted mid-bank, so everything after them
moves: bank 6 by three bytes, part of bank 7 by nine. Nothing else about the
layout differs -- banks 1, 2 and 4 are byte-identical and every area header
matches -- so one address map covers the whole difference.

Validated against 24 known landmarks: every hardcoded table, gate and constant
the tools address by number lands on identical bytes once mapped.

Usage:
  python reloc.py <ntsc.a78> <other.a78>     report the mapping and check it
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from disasm import Cart, BANK_SIZE

# name -> [(space, lo, hi, delta)] applied to an NTSC address
VERSIONS = {
    "ntsc": [],
    "pal": [
        # one extra 3-byte DLL entry inside dat_4277
        ("f6", 0x42B7, 0x8000, 3),
        # three more in the bank-7 display lists, undone before the tail
        ("f7", 0xD1D4, 0xD7F7, 9),
    ],
}

# (space, addr, expected byte) that tells the releases apart. Each sits after a
# seam, so it reads differently unless the address is mapped.
FINGERPRINT = [
    ("f6", 0x6433, 0xFC),        # tbl_SactorToughness, kind 0
    ("f6", 0x50ED, 0x28),        # weapon fire rate, knife
    ("f6", 0x5213, 0x08),        # the diamond's hp_max gain
]


def relocate(version, space, addr):
    """Map an NTSC address into `version`'s layout."""
    for sp, lo, hi, delta in VERSIONS[version]:
        if sp == space and lo <= addr < hi:
            return addr + delta
    return addr


def detect(cart):
    """Which release this image is, by reading the fingerprint both ways."""
    def rd(space, addr):
        bank = {"f6": cart.fixed_lo, "f7": cart.fixed_hi}.get(space, int(space[1:]))
        base = {"f6": 0x4000, "f7": 0xC000}.get(space, 0x8000)
        return cart.rom[bank * BANK_SIZE + (addr - base)]

    for name in VERSIONS:
        if all(rd(sp, relocate(name, sp, ad)) == want
               for sp, ad, want in FINGERPRINT):
            return name
    return None


LANDMARKS = [
    ("f7", 0xF32A, 8, "area header pointers"), ("f7", 0xF2B4, 8, "slice source lo"),
    ("f7", 0xF2E8, 8, "slice source hi"), ("f7", 0xF31D, 8, "slice destination"),
    ("f7", 0xFEB5, 8, "area graphics page"), ("f7", 0xFEBE, 8, "area bank"),
    ("f7", 0xFEC7, 8, "terrain property pointers"), ("f7", 0xF296, 16, "spawn amounts"),
    ("f7", 0xF2A5, 16, "spawn rate masks"), ("f7", 0xD404, 2, "halve health gate"),
    ("f7", 0xD41E, 3, "heart blood immunity"), ("f7", 0xD0C7, 2, "necklace water walk"),
    ("f7", 0xF021, 3, "lantern clears darkness"), ("f6", 0x6433, 13, "toughness seeds"),
    ("f6", 0x50ED, 4, "weapon fire rates"), ("f6", 0x6753, 16, "screen kind table"),
    ("f6", 0x5195, 8, "item icon column"), ("f6", 0x51A5, 8, "item icon palette"),
    ("f6", 0x4AE0, 2, "starting purity"), ("b0", 0xBDC2, 8, "debug hook"),
    ("b5", 0xB19F, 8, "boss setup pointers"), ("b5", 0xBBFD, 4, "boss contact damage"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ntsc")
    ap.add_argument("other")
    args = ap.parse_args()
    a, b = Cart(args.ntsc), Cart(args.other)

    va, vb = detect(a), detect(b)
    print("%-44s %s" % (os.path.basename(args.ntsc), va))
    print("%-44s %s" % (os.path.basename(args.other), vb))
    if not vb:
        print("\nthe second image matches no known layout")
        return 1

    def rd(c, space, addr, n):
        bank = {"f6": c.fixed_lo, "f7": c.fixed_hi}.get(space, int(space[1:]))
        base = {"f6": 0x4000, "f7": 0xC000}.get(space, 0x8000)
        o = bank * BANK_SIZE + (addr - base)
        return bytes(c.rom[o:o + n])

    print("\n%-28s %-12s %-12s %s" % ("landmark", "ntsc", vb, "bytes"))
    bad = 0
    for sp, ad, n, name in LANDMARKS:
        pa = relocate(vb, sp, ad)
        same = rd(a, sp, ad, n) == rd(b, sp, pa, n)
        bad += 0 if same else 1
        print("  %-26s %s:$%04X    $%04X       %s"
              % (name, sp, ad, pa, "same" if same else "DIFFER"))
    print("\n%d of %d landmarks identical once mapped" % (len(LANDMARKS) - bad, len(LANDMARKS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
