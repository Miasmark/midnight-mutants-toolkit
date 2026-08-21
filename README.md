# Midnight Mutants — editor, tools and patches

A ROM editor, reference documentation and a repair patch for **Midnight Mutants**
(Atari 7800, Atari Corp., 1990), built on a complete, byte-verified disassembly
of the cartridge.

**No ROM data is included.** Everything here operates on a cartridge image you
supply. No disassembly listings are included either — the editor regenerates
them on demand from the annotation files, so nothing here reproduces the game's
code or artwork.

---

## Requirements

* **Python 3.7 or newer.** The editor and the disassembler chain need nothing
  but the standard library — verified by running them with Pillow blocked.
  (Developed and tested on 3.10.)
* *Optional:* **Pillow**, only for the four tools that write image files:
  `gfx.py`, `sprites.py`, `animate.py` and `arenas.py`. Nothing else imports it.
* **A modern browser.** The editor is a local web application; it serves to
  `127.0.0.1` and never talks to the network.
* **A Midnight Mutants cartridge image**, NTSC or PAL, with or without the
  128-byte `.a78` header. Both regions are fully supported.
* *Optional:* **MAME** with the 7800 BIOS, if you want to run what you build.
  `a7800` is the NTSC machine, `a7800p` the PAL one.

## Quick start

```
python tools/editor.py "Midnight Mutants (NTSC) (Atari) (1990).a78"
```

That opens the editor in your browser. Load a cartridge, change things, and use
**Export patch** to write a `.bps` you can share — or **Save as** for a complete
image. Nothing is written to the original file unless you ask.

To apply the ready-made repair pack instead of editing anything, use **Load
.bps** in the editor and point it at `patches/mm-pack-ntsc.bps` (or `-pal`).

## What's in here

| | |
|---|---|
| `tools/` | The editor and the code it needs. `editor.py` is the server, `romedit.py` the whole write layer, `editor_ui/` the front end &mdash; plus the disassembler chain (`disasm.py`, `asm.py`, `verify.py`, `build.py`) and the analysis tools the docs refer to: `gfx.py` and `sprites.py` for artwork, `map.py` and `rammap.py` for memory, `text.py`, `arenas.py`, `patch.py`. |
| `docs/` | Fifteen reference documents — the format of every structure in the cartridge, and how it was established. Start with `EDITOR.md`. |
| `site/` | Eight self-contained HTML pages: the disassembly report, room maps, bestiary, items, bosses, sprite sheet, editor manual, version comparison. Open `site/index.html`. |
| `patches/` | The repair-and-tweak pack for both regions, its notes, and the script that builds it. |
| `annotations*.json` | Every human judgement about the ROM — labels, comments, data-block declarations — for NTSC and PAL. The disassembler is driven entirely from these. |
| `build/` | Two small data files the editor reads: the sprite catalogue and the region table. Also where it writes audio previews. |

### The editor

A local web app. It edits the cartridge in place and shows you the byte cost of
everything, so you always know what a change actually did:

* **Rooms** — layouts, widths, exits and their conditions, spawns, items,
  doors, terrain. Overlays for collision, water and exit destinations.
* **Items, bosses, actors** — toughness, contact damage, weak spots, portraits,
  behaviour rules, the health and blood-purity economies.
* **Text** — all 114 records, including the terminator byte that decides whether
  a message shimmers, and the hold duration.
* **Graphics and sound** — palettes, sprite and character cells pixel by pixel,
  sound effects and music.
* **Repairs and tweaks** — a checkbox for each of the fixes described in
  `patches/mm-pack.md`, applied and reverted independently.
* **Disassemble** — regenerates the full annotated listing from the *edited*
  image, so you can read exactly what you changed.

Patches are built against the **cartridge data only**, with the `.a78` header
excluded, so one patch serves every dump of its region regardless of which
header the file carries.

### The patch pack

`patches/mm-pack-{ntsc,pal}.bps` — repairs for things the shipped cartridge got
wrong (a debug cheat that soft-reboots the console, three broken inventory
icons, two animation tables read one entry past their end, a targeting reticle
drawn as a corpse's leg, the mega blaster's two unused frames, four pickup
messages that never shimmer, and on PAL the music tempo that was never retimed),
plus a small set of deliberate changes. `patches/mm-pack.md` lists every one with
its byte cost and reasoning.

Read that file before applying — it explains that the patches are headerless and
how to apply them outside the editor.

## Proving it to yourself

Nothing here asks to be taken on trust. The disassembler regenerates the full
listing from the annotations, and the assembler puts it back together — if the
result is not the byte-for-byte original, something is wrong and it says so:

```
python tools/disasm.py "<your rom>.a78" -c annotations.json -o src
python tools/verify.py "<your rom>.a78" -d src
  f6   OK    16384 bytes reassemble identically
  ...
  ROUND-TRIP PASSED
```

The same works for PAL with `-c annotations-pal.json`. That round trip is the
discipline the whole project rests on: it proves the disassembly accounts for
every byte in the cartridge, which is what makes it safe to edit one.

`src/` is not shipped — it is output, and it is yours to generate.

## Notes

* The editor never modifies your source image unless you explicitly save over it.
* PAL and NTSC are genuinely different builds, not one ROM with a switch; the
  tools carry separate annotations and address maps for each. `docs/VERSIONS.md`
  covers the differences.
* If a change looks wrong in game, `docs/` almost certainly explains the
  structure involved — the documentation exists because each of those structures
  had to be worked out before it could be edited safely.

---

## Credits

**Midnight Mutants** — Atari 7800, 1990. The game's own title sequence credits:

> `PROGRAM AND DESIGN BY PETER ADAMS`
> `COPYRIGHT 1990 ATARI CORP — ALL RIGHTS RESERVED`

The author signed the game twice more inside it: the mansion's backstory names
"Professor Von Adams", and one of Grampa's lines is *"IT'S A WONDER PETER EVER
GOT THIS PROGRAM BEDUGGED!"*

Midnight Mutants, its code, artwork and characters remain the property of their
respective rights holders. This package contains none of them — only tools that
operate on a copy you already own, documentation describing how the cartridge is
structured, and patches expressed as differences.

## Citations and acknowledgements

* **MAME** (mamedev.org) — every behavioural claim in the documentation was
  checked against the game running under MAME's `a7800`/`a7800p` drivers, using
  scripted probes and input recordings rather than inspection alone.
* **The BPS patch format**, created by byuu/near for the *beat* patcher.
  `tools/bps.py` is an independent implementation; patches it produces are
  readable by Floating IPS, RomPatcher.js and other standard tools.
* **Trebor's 7800 ROM PROPack** (AtariAge) — used to cross-check cartridge dumps
  across regions and to confirm that the two PAL images in circulation hold
  identical cartridge data and differ only in a header field.
* **The `.a78` header format** — the standard 7800 cartridge header, as used by
  MAME and the wider 7800 community.
* **Atari 7800 / MARIA hardware documentation** — the MARIA display processor
  specification and the 7800 software guide, for display lists, holey DMA and
  the graphics read modes.
* The Atari 7800 homebrew and preservation community, whose accumulated notes on
  cartridge mappers and hardware behaviour made the early going much faster.

Where this project's findings disagree with published references, the
disagreement is documented in `docs/` along with the evidence for it.

## Licensing

The tools, documentation and patches here are **MIT licensed** — see `LICENSE`.
Use them, change them, ship them; keep the copyright notice.

That licence covers this repository's own work and nothing else. Midnight
Mutants belongs to its rights holders, and none of it is here: no cartridge
data, no disassembly listings. The patches are differences, and they are
meaningless without a copy of the game you already own. If you fork this, keep
it ROM-free — that is the condition under which it is safe to share.
