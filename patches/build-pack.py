#!/usr/bin/env python3
"""Build the repair-and-tweak pack for both regions.

Run from anywhere; paths are resolved relative to this file. Produces
mm-pack-<region>.a78 and a headerless mm-pack-<region>.bps beside it.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "disasm", "tools"))
from romedit import RomEdit

SRC = {
    "ntsc": "Midnight Mutants/Midnight Mutants (NTSC) (Atari) (1990).a78",
    "pal":  "Midnight Mutants/Midnight Mutants (Europe).a78",
}
LIBRARY = 0x4F                      # the room with the two bookshelves
DIAMOND, ZOMBIE10 = 8, 10

def build(region, path):
    r = RomEdit(os.path.join(ROOT, path))
    r.set_compact_flip(True)         # frees a 28-byte pocket, keeps the tail whole

    # ---- repairs
    r.set_debug_hook(True)           # PAUSE + four presses no longer soft-reboots
    r.set_icon_fixes(True)           # crypt key / necklace / pumpkin icons
    r.set_reticle_leg(True)          # targeting bracket drawn as a corpse's leg
    r.set_actor_death(True)          # dat_5CE6 overrun
    r.set_ghost_death(True)          # dat_6219 overrun
    r.set_mega_frames(True)          # $A8/$AA, the two frames it never showed

    # ---- changes
    r.set_purity_necklace(True)      # halve-health gate: cross -> necklace
    r.set_rule("sactor_contact", 8)  # 16 -> 8, to go with the gate move
    r.set_toughness(ZOMBIE10, 0xF4)  # $00 overflows instantly and left it inert
    r.set_item(LIBRARY, iid=DIAMOND, x=0x50, y=0x74)
    # Order matters: the 28-byte pocket fits exactly one shim, and water walk
    # is the one that leaves the tail's free run longest. Taking it second costs
    # PAL nine bytes; taking it third does not fit at all.
    r.set_water_walk(True)           # terrain bit 2 instead of a room-$01 position test
    if region == "pal":
        r.set_music_retick(True)     # 83.3% speed -> an extra tick every 5th frame
    r.set_pumpkin_hint(True)         # kind 5 was the only silent pickup
    r.set_pickup_shimmer(True)       # cross + axe + blaster + mega ended $FF
    r.set_axe_spin(True)             # three poses at half speed
    r.set_axe_fourth(True)           # a fourth: $CE mirrored into $88

    a78 = os.path.join(HERE, "mm-pack-%s.a78" % region)
    bps = os.path.join(HERE, "mm-pack-%s.bps" % region)
    r.save(a78)
    r.export_patch(bps, note="Midnight Mutants repair and tweak pack (%s)" % region.upper())
    f = r.free_space()
    print("%-5s %3d bytes changed | patch %3d B | free %d of %d (largest run %d)"
          % (region, len(r.changes()), os.path.getsize(bps),
             f["free_total"], f["total"], f["contiguous"]))
    return r

if __name__ == "__main__":
    for region, path in SRC.items():
        build(region, path)
