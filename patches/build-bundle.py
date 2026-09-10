#!/usr/bin/env python3
"""Build the repair-and-tweak pack as an .abp, so it can be picked from.

`build-pack.py` fuses every repair and every change into one BPS per
region. That is the right shape for "here is the pack" and the wrong shape
for what the pack's own documentation actually offers: a table of thirteen
separate things, each with its own byte cost, most of which somebody might
reasonably want without the others. Wanting the icon fixes and not the
water-walk change currently means editing this directory and rebuilding.

So the same edits also go out as an anchored bundle of patches. Each
toggle becomes one option; each contiguous run of bytes it changes becomes
a section carrying a CRC32 of what it expects to find. Then:

    python tools/patchset.py list patches/mm-<region>.abp
    python tools/patchset.py apply patches/mm-<region>.abp \\
        --rom "Midnight Mutants (NTSC) (Atari) (1990).a78" \\
        --with icon-fixes,reticle-leg,mega-frames --out fixed.a78

Nothing is lost by doing it this way. Ask for everything and you get the
pack; the monolithic BPS files stay where they are for anyone who wants
exactly that.

## What is in the bundle and what is not

Every toggle that is a plain on/off and applies to a pristine cartridge on
its own. Deliberately excluded, and worth stating so the absence is not
mistaken for an oversight:

  - `set_purity_necklace` and `set_rule("sactor_contact", 8)` are one
    change in two calls -- the gate moves from the cross to the necklace
    and the contact rule moves with it -- and the first takes arguments
    this script would have to guess at. They belong together in one option
    once somebody who knows the intent writes it.
  - `set_toughness` and `set_item` take values rather than switches, so
    they are settings, not options.
  - `set_music_retick` is PAL only and refuses an NTSC cartridge, which is
    correct; it appears in the PAL bundle alone.

## Signing

The NTSC bundle's output is signed by `patchset.py` on the way out; the
PAL bundle's is not, because no PAL console checks and the retail PAL
cartridge carries `$FF` where a signature would go. Each bundle declares
its region so that holds for a headerless dump too, which has no `.a78`
TV byte to read.

## A note on addresses

A 128K bankswitched cartridge has no single CPU address for a file offset,
so this bundle uses **file offsets** with `base` at 0 rather than
pretending otherwise. Sections are byte ranges either way, and the format
does not care which coordinate they are in as long as it is consistent.
"""
import io
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bps                      # noqa: E402
import patchset                 # noqa: E402
from romedit import RomEdit     # noqa: E402

SRC = {
    "ntsc": "Midnight Mutants/Midnight Mutants (NTSC) (Atari) (1990).a78",
    "pal": "Midnight Mutants/Midnight Mutants (Europe).a78",
}

# id, method, title, which regions, and the note the patcher shows
OPTIONS = [
    ("compact-flip", "set_compact_flip", "repack the flip table",
     "both", "Frees a 28-byte pocket and keeps the tail whole. Wanted by "
             "anything that needs free space."),
    ("debug-hook", "set_debug_hook", "PAUSE plus four presses stops rebooting",
     "both", "Two of the four counter states branched into data, and so did "
             "both wrong-button exits; the IRQ vector is the reset entry, so "
             "each was a soft reboot."),
    ("icon-fixes", "set_icon_fixes", "crypt key, necklace and pumpkin icons",
     "both", "The key was invisible and the necklace a smudge, both drawn on "
             "a palette whose first colour is pure black; the pumpkin showed "
             "the heart's icon."),
    ("reticle-leg", "set_reticle_leg", "the corpse that grew a targeting bracket",
     "both", "The last frame of a special actor's death drew the Grampa "
             "screen's reticle as its right leg."),
    ("actor-death", "set_actor_death", "crow, bat, ground and spider death frame",
     "both", "dat_5CE6 is one entry shorter than the seed allows, so the "
             "first frame reads the following routine's opcode."),
    ("ghost-death", "set_ghost_death", "ghost death frame",
     "both", "dat_6219, the same overrun as actor-death."),
    ("mega-frames", "set_mega_frames", "the mega blaster's two lost frames",
     "both", "It asks for four phases and its run repeats two; $A8/$AA hold "
             "the other two, referenced by nothing."),
    ("pickup-shimmer", "set_pickup_shimmer", "four pickups that never shimmered",
     "both", "A message's terminator decides whether the banner pulses. The "
             "cross and the three weapons above the knife end $FF; every "
             "other pickup ends $FE."),
    ("pumpkin-hint", "set_pumpkin_hint", "the plasmic pumpkin says something",
     "both", "Kind 5 was the only silent pickup in the game."),
    ("water-walk", "set_water_walk", "water is water everywhere",
     "both", "Terrain bit 2 instead of a position test against room $01."),
    ("axe-spin", "set_axe_spin", "the axe spins at full speed",
     "both", "Three poses were played at half rate."),
    ("axe-fourth", "set_axe_fourth", "a fourth axe pose",
     "both", "$CE mirrored into $88."),
    ("music-retick", "set_music_retick", "PAL music at the right tempo",
     "pal", "Durations are frame counts and the European release was never "
            "retimed, so everything played at 83.3% speed. An extra tick "
            "every fifth frame, from a shim in free space."),
]


def runs(changes):
    """Contiguous runs of changed offsets, as (start, length)."""
    out = []
    for off, _before, _after in changes:
        if out and off == out[-1][0] + out[-1][1]:
            out[-1][1] += 1
        else:
            out.append([off, 1])
    return [(a, n) for a, n in out]


def build(region, rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        print("  %s: no cartridge at %s -- skipped" % (region, rel))
        return None
    base = RomEdit(path)
    body = bytes(base.original)

    sections, files, options = {}, {}, []
    for oid, meth, title, where, note in OPTIONS:
        if where != "both" and where != region:
            continue
        r = RomEdit(path)
        try:
            getattr(r, meth)(True)
        except Exception as e:                      # a toggle this region refuses
            print("  %-15s skipped: %s" % (oid, str(e)[:60]))
            continue
        after = bytes(r.rom)
        touched = []
        for at, n in runs(r.changes()):
            sid = "s_%06X_%d" % (at, n)
            sections[sid] = {
                "addr": at, "length": n,
                "crc32": "0x%08X" % (zlib.crc32(body[at:at + n]) & 0xFFFFFFFF),
                "what": title,
            }
            member = "p/%s.%s.bps" % (oid, sid)
            files[member] = bps.create(body[at:at + n], after[at:at + n])
            touched.append((sid, member))
        options.append({
            "id": oid, "title": title, "note": note,
            "patches": {sid: {"bps": member} for sid, member in touched},
        })
        print("  %-15s %3d bytes in %d section(s)"
              % (oid, sum(sections[s]["length"] for s, _ in touched),
                 len(touched)))

    # anchors: ranges no option touches, so they identify the cartridge
    # without being a hash of a file every patch changes
    used = set()
    for s in sections.values():
        used.update(range(s["addr"], s["addr"] + s["length"]))
    anchors = []
    for at in (0x0000, 0x8000, 0x1C000):
        if not (set(range(at, at + 256)) & used):
            anchors.append({"addr": at, "length": 256,
                            "crc32": "0x%08X"
                                     % (zlib.crc32(body[at:at + 256])
                                        & 0xFFFFFFFF)})

    manifest = {
        "format": patchset.FORMAT,
        "name": "Midnight Mutants repairs and tweaks (%s)" % region.upper(),
        "what": "The repair-and-tweak pack, one option per change, so it can "
                "be picked from rather than taken whole.",
        "target": {
            "what": os.path.basename(rel),
            "body_size": len(body),
            "body_sha256": __import__("hashlib").sha256(body).hexdigest(),
            "headers": [0, 128],
            # A headerless dump carries no TV byte, and the region cannot
            # be recovered from the bytes -- an unsigned NTSC cartridge and
            # a PAL one are both $FF where a signature would go. So the
            # bundle is where that fact has to live: it was built for one
            # cartridge and says which, and that survives the header being
            # stripped off the file it is handed.
            "region": region,
            "base": 0,
            "anchors": anchors,
        },
        "knobs": {},
        "sections": sections,
        "options": options,
    }
    out = os.path.join(HERE, "mm-%s.abp" % region)
    patchset.write_bundle(out, manifest, files)
    print("  -> %s  (%d options, %d sections, %d bytes)"
          % (os.path.basename(out), len(options), len(sections),
             os.path.getsize(out)))
    return out


def main():
    for region, rel in SRC.items():
        print("%s:" % region)
        build(region, rel)


if __name__ == "__main__":
    main()
