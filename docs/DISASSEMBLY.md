# Midnight Mutants (NTSC, Atari, 1990) — disassembly

A bank-aware, annotated disassembly of the Atari 7800 cartridge, with tooling to
regenerate and **verify** it.

> **In this package the listings are generated, not shipped.** There is no `src/`
> directory until you make one — either with the editor's **Disassemble** button
> or with the command below. Everything in this document then applies to what it
> produced.
>
> ```
> python tools/disasm.py "<your rom>.a78" -c annotations.json -o src
> python tools/verify.py "<your rom>.a78" -d src      # must say PASSED
> python tools/build.py  "<your rom>.a78" -d src -o rebuilt.a78
> ```

The headline property: `tools/build.py` reassembles the listings in `src/` back
into a byte-identical 131,200-byte `.a78`. Same MD5 as the original ROM. Every
claim in here rests on that round trip.

```
$ python tools/verify.py "../Midnight Mutants/Midnight Mutants (NTSC) (Atari) (1990).a78"
  b0   OK    16384 bytes reassemble identically
  ...
  ROUND-TRIP PASSED

$ python tools/build.py "../Midnight Mutants/Midnight Mutants (NTSC) (Atari) (1990).a78"
  wrote build/rebuilt.a78 (131200 bytes)
  identical to reference ROM: YES
```

## Layout

> **The `build/` rows below are generated output, and this package ships almost
> none of it** — the renders, the maps, the WAVs and the rebuilt image are all
> produced by running the tools against your own cartridge. The two small files
> that *are* shipped in `build/` (`_spritenames.py` and `regions.json`) are
> hand-maintained data the editor reads, not output.


| path | what |
|---|---|
| `src-pal/` | The European disassembly, same nine listings, also byte-identical on rebuild |
| `src/f6.asm` | ROM bank 6 at `$4000` — vector table, DLI handlers, main loop, item and terrain logic |
| `src/f7.asm` | ROM bank 7 at `$C000` — sprites, the `$D000` service table, area descriptors, RESET |
| `src/b0.asm` | ROM bank 0 — sound engine, text renderer, message selector, the whole script |
| `src/b1.asm`, `b2.asm`, `b4.asm` | area graphics and map data; no code reached |
| `src/b3.asm` | code at `$8000`, character sets from `$9000`, the palette block |
| `src/b5.asm` | code at `$B000`-`$BBFF`, scenery art at `$A000`, boss sequences |
| `src/b7.asm` | bank 7 assembled at `$8000`, for when it is paged into the window |
| `annotations.json` | **the only hand-edited file** — labels, comments, data blocks, RAM names, bank hints |
| `COVERAGE.md` | **what has been established, measured by bank** |
| `MEMORY_MAP.md` | page-by-page map of all 128K |
| `RAM_MAP.md` | every RAM/IO address the traced code touches, with reference counts |
| `AREAS.md` | every room's header: graphics page, darkness, map limit, exits |
| `ITEMS.md` | every inventory slot and every place that reads it |
| `ACTORS.md` | enemies, damage, spawning, the cross, palettes |
| `SPRITES.md` | how creatures are stored, assembled, animated and coloured |
| `BOSSES.md` | the three fights: setup records, per-boss routines, the difficulty ramp |
| `PLAYER.md` | movement, collision, firing, the Grampa screen and its message chain |
| `SOUND.md` | both audio engines &mdash; effects in bank 0, the two-voice tracker in bank 6 |
| `TEXT.md` | every dialogue/story record, decoded |
| `SCREENS.md` | per-screen record streams |
| `build/maps/` | one terrain map per room, plus `MAPS.md` and `MAPGRAPH.md` |
| `build/worldmap.svg` | the whole world as one diagram |
| `build/gfx/*.png` | extracted character sets and sprite sheets |
| `build/sprites/` | every actor cell, rendered |
| `build/rooms/` | all 76 rooms rendered in colour, items placed |
| `build/arenas/` | the three boss portraits |
| `build/music/` | every song rendered to WAV, plus an instrument demo |
| `build/palette_chart.png` | all 256 colour bytes, for checking against a display |
| `build/rebuilt.a78` | the cartridge rebuilt from `src/` — byte-identical to the original |

## Where the reference lives

Published pages carry the results in visual form:

* the reference &mdash; verification, banking, the map model, mechanics
* the bestiary &mdash; every creature, animated, with stats and spawn rooms
* the rooms &mdash; all 76 drawn from the cartridge, with items, spawns, exits and doors
* the bosses &mdash; portraits, weak points, projectiles and the escalation rules
* the items &mdash; every slot, its icon, where it is and what reads it
* the sprite sheet &mdash; every actor cell, identified
* the editor manual &mdash; the eleven panels, what is shared, what it refuses
* NTSC and PAL &mdash; how the two releases differ, and why almost none of it is the game

`tools/mksite.py` packages the set into `site/` as a standalone folder with the
links rewritten to relative filenames, so it browses offline.

## Versions

`VERSIONS.md` compares the NTSC and European releases. They differ in 12.6% of
their bytes, but almost all of that is one relocation: the European display list
gains zones for PAL's taller screen, shifting bank 6 by +3 and part of bank 7 by
+9. Every gameplay constant, all 76 area headers and banks 1, 2 and 4 are
byte-identical, so the two play the same.

## Editing the cartridge

The disassembly has a write side: `tools/editor.py` is a GUI for changing rooms,
terrain, items and exits, saving a runnable `.a78`. See `EDITOR.md`.

```
python tools/editor.py "Midnight Mutants (NTSC) (Atari) (1990).a78"
```

Windows shortcuts sit beside the cartridge folder: `Edit Cartridge.bat` and
`Edit PAL Cartridge.bat` open the editor, `Play Midnight Mutants.bat [pal]`
and `Play PAL Test Build.bat <name>` run MAME on the matching system.

## Toolchain

| tool | what it does |
|---|---|
| `editor.py` | GUI cartridge editor: rooms, terrain, items and exits, over a local server. See `EDITOR.md`. |
| `bps.py` | Reads and writes BPS patches -- changed bytes only, with CRC32 of source, target and patch. Usable standalone. |
| `slack.py` | Finds code that could be encoded smaller, and flags what sits in timing-critical regions. |
| `reloc.py` | Identifies NTSC vs European and maps addresses between them. |
| `romedit.py` | The write side -- a mutable `Cart` with structured, in-place accessors that refuse any edit that would move data. |
| `mksite.py` | Packages the published pages into `site/` as a standalone folder. |
| `disasm.py` | Bank-aware recursive-descent disassembler. Tracks A/X/Y constants to resolve bank switches, auto-discovers the DLI chain, applies `annotations.json`. |
| `asm.py` | A 6502 assembler for exactly the dialect `disasm.py` emits. |
| `verify.py` | Reassembles every listing and compares against the original bank. |
| `build.py` | Assembles all eight banks into a complete `.a78` and diffs it against the ROM. |
| `map.py` | Generates `MEMORY_MAP.md`. |
| `rammap.py` | Generates `RAM_MAP.md`. |
| `text.py` | Decodes the text records; can emit data blocks for `annotations.json`. |
| `gfx.py` | Renders character sets to PNG. |
| `rooms.py` | Renders any room in colour &mdash; terrain, charset, palette, item. |
| `arenas.py` | Renders the three boss portraits. |
| `areas.py` | Parses every area header: exits on four edges, cast, item, terrain slices. |
| `music.py` | Decodes the song tables and renders any song to WAV. |
| `palette.py` | Colour-byte conversion, the flash generator, observed overrides. |
| `mkroompage.py`, `mkbosspage.py`, `mkitempage.py` | Build the room, boss and item pages. |
| `recon.py` | First look: `.a78` header, per-bank entropy, vectors. |
| `mkpage.py` | Generates `build/report.html`. *(Not in this package: it builds from a `pages/` tree that is not shipped.)* |
| `mame/run.lua` | Drives the cart in MAME and dumps display/player state at chosen frames. |
| `mame/watch.lua` | Samples all RAM at intervals so slow state can be found by diffing. |

`asm.py` exists so the disassembly can be checked rather than trusted. It has
already caught a stale bank in the tracer, a label swallowed by a data block, and
a call attributed to the wrong bank.

Regenerate everything:

```
python tools/disasm.py <rom.a78> -c annotations.json -o src
python tools/map.py    <rom.a78> -c annotations.json -o MEMORY_MAP.md
python tools/rammap.py <rom.a78> -c annotations.json -o RAM_MAP.md
python tools/text.py   <rom.a78> -o TEXT.md
python tools/verify.py <rom.a78>          # must print ROUND-TRIP PASSED
python tools/build.py  <rom.a78>          # must print identical: YES
python tools/mkpage.py
```

## Cartridge

128K SuperGame, NTSC, joystick. The `.a78` header says cart type `$0012`
(SuperGame + bank 6 at `$4000`); `ProSystem.dat` independently lists this MD5 as
`type=4`. Both were confirmed empirically rather than trusted: RESET ends in
`JMP $4000` and `$4000` holds a valid JMP table, which only works under this
mapping.

```
$4000-$7FFF   ROM bank 6, fixed     engine: vector table, DLI handlers, game logic
$8000-$BFFF   ROM bank 0..7, paged  any write to $8000-$FFFF selects the bank
$C000-$FFFF   ROM bank 7, fixed     graphics, service jump table, area tables, RESET
```

| bank | role |
|---|---|
| 0 | text renderer (`$A2xx`) + the entire dialogue/story script (`$A6A3`-`$BFFF`) |
| 1, 2, 4 | area graphics and map data — no code |
| 3 | code at `$8000`, graphics from `$9000` |
| 5 | code at `$B000`-`$BBFF`, scenery art at `$A000` |
| 6 | main engine (fixed at `$4000`) |
| 7 | sprites at `$C000`, service routines `$D000`+, area tables, RESET |

Two fixed jump tables are the ABI between banks, since only they are always
mapped: `$4000` (5 slots, bank 6) and `$D000` (23 slots, bank 7).

## Boot

```
RESET ($FF00)
  LDA #$07 / STA INPTCTRL   ; 7800 mode, MARIA on, BIOS ROM out
  CLI / CLD
  LDA #$7F / STA CTRL       ; MARIA DMA off during init
  LDX #$FF / TXS
  STA $8000                 ; select bank 0
  STA $BF                   ;   ...and shadow it in cur_bank
  STA OFFSET
  clear zero page $40-$FF   ; $00-$3F is TIA/MARIA, not RAM
  JMP $4000                 ; into the engine via the bank-6 table
```

`$BF` shadowing the selected bank matters: interrupt handlers page in bank 0 to
do their work and restore `$BF` afterwards.

## Display

MARIA `CTRL = $50` — DMA on, one-byte characters, read mode 00 (160×2/160×4).
The display list list lives at `$0140` in RAM (`DPPH/DPPL`).

NMI is MARIA's display-list interrupt. `$400C` is `JMP ($2135)`, an indirect
jump through RAM, so each DLI installs the handler for the next zone. The chain
is three handlers, and `tools/disasm.py` rediscovers it automatically by
scanning for `LDA #lo / STA $2135` pairs:

| handler | job |
|---|---|
| `$4104` | top of frame; sets up palettes, arms `$416F` |
| `$416F` | one instruction — `DEC $1E68` — a raster sync tick |
| `$400F` | per-zone palette swap, 11 zones, 4 bytes per zone from `$1ECC` |

The `$416F` trick is worth a look. Foreground code at `$4150` does:

```
LDA cur_bank        ; hold the bank we want restored
L_4152:
BIT $1E68
BEQ L_4152          ; spin until the sync DLI fires
STA $8000           ; now safe to page the bank back in
```

It parks the CPU until the raster has passed the zone, then swaps banks — bank
switching mid-zone would pull the graphics out from under MARIA.

## Graphics format

In character-map mode MARIA forms a character's address as
`((CHARBASE + line) << 8) | char_number`, so character sets are **line-planar**:
page `CHARBASE+0` holds line 0 of all 256 characters, `CHARBASE+1` holds line 1,
etc. At 160×2 each byte is four 2-bit pixels (MSB first), so one character is
4 pixels wide.

`CHARBASE` is loaded from `area_page` (`$1FCF`), which is `$80` or `$A0` — the
two halves of the paged window. `tools/gfx.py` renders these; see `build/gfx/`.

Colour is not in the ROM at these addresses — it comes from the MARIA palette
registers at run time, so the sheets render as raw 2-bit indices. The startup
palette is a 24-byte table at `$4D1B` copied into MARIA `$28-$3F`, skipping
every fourth register because those slots are control registers, not colours.

## Areas

Nine descriptor slots (index 0 unused) at `$FEB5`-`$FEE1` in bank 7, five
parallel tables:

| index | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| `$FEB5` page | $80 | $A0 | $80 | $A0 | $80 | $A0 | $80 | $A0 |
| `$FEBE` bank | 1 | 1 | 2 | 2 | 3 | 3 | 4 | 4 |
| `$FED0/$FEC7` ptr | $DA00 | $DA80 | $DB00 | $DB80 | $DA80 | $DA80 | $DC00 | $DC80 |
| `$FED9` type | 1 | 1 | 8 | 8 | 1 | 1 | 9 | 8 |

Eight areas across four banks, two per bank — one in each half of the window.
`$1FCF` carries the area index in, and the entry code at `$F178` overwrites it
with the page byte, after which it is used as the `CHARBASE` high byte.

## Text

Dialogue is plain uppercase ASCII in records:

```
$FF <p1> <p2> '@' <text> '#'
```

Control codes, confirmed against the renderer at `b0:$A22F`-`$A2D1`:

| byte | char | meaning |
|---|---|---|
| `$40` | `@` | start of text |
| `$23` | `#` | end of text |
| `$7C` | `\|` | newline — renderer adds `$16` to the destination pointer, so **22 columns** |
| `$26` | `&` | new page — reset column, then newline |
| `$2A` | `*` | draw glyph `$3C` |
| `$5E` | `^` | apostrophe |

48 records: 43 in bank 0 (`$A6A3`-`$BFFF`) and 5 in bank 6 near `$6BBF`.
`$A2AC` is the classifier: carry set for a break
character (space, `\|`, `*`, `&`, or anything `>= $80`), clear for a glyph.

## Game state

| addr | name | meaning |
|---|---|---|
| `$C4` | `blood_purity` | starts 100; 0 = undead ending |
| `$C5` | `hp_cur` | current health; 0 = death |
| `$C6` | `hp_max` | maximum health, starts `$27` (39) |
| `$8B` | `death_state` | `$FF` on death, counts down during the death animation |
| `$1FD3` | `revive_ok` | latched while alive; lets Grampa resurrect you |
| `$1FD5` | `undead_flag` | set when blood purity hits 0 |
| `$1F3D+n` | `inventory` | per-item counters, indexed by `item_type` (`$1E80`) |

`hp_max` moves in three places: **+8 for a diamond** (item type `$08`,
`f6:$520F`), **+$10 at the end of the bank-5 sequence** (`b5:$B637`, which also
refills blood purity), and **-8** at `f6:$5890`. It is not touched by the health
well.

### Grampa's dialogue

`GrampaPickMessage` (`b0:$A32B`) returns an index into the 50-entry pointer table
at `$A608`/`$A63A`. First match wins:

| test | message |
|---|---|
| `forced_msg != 0` | `(forced_msg & $7F) \| $20` |
| `undead_flag != 0` | `$0C` "YOU'RE ONE OF THE UNDEAD" |
| `win_flag > 0` | `$0D` "OH WHAT A RELIEF! YOU SAVED ME!" |
| `death_state != 0`, `revive_ok == 0` | `$0B` "HIT RESET TO RESTART" |
| `death_state != 0`, `revive_ok != 0` | `$0F` resurrection |
| otherwise | the hint pool |

`revive_ok` is latched by `StatusTick` (`f6:$4E8E`, every 8th frame) only while
`blood_purity != 0`, `hp_max >= $30` and `mode_flag == 0`. Since `hp_max` starts
at 39, resurrection is unavailable until diamonds push it to 48. The revive then
halves `hp_max`, so it is roughly self-limiting. Dying of blood poisoning sets
`undead_flag` instead and can never be resurrected — which is what the message
itself says.

### Items and terrain

Item numbers index the inventory counters at `$1F3D` (16 slots, slot 0 unused)
and the icon tables at `$5195`/`$51A5`. Confirmed from code:

| item | effect | where |
|---|---|---|
| `$05` | destroys terrain `$EF`, sets `win_flag` | `f6:$575C` |
| `$06` | red potion: blood purity +50, capped at 100 | `f6:$508B`, `f6:$5236` |
| `$07` | blue potion: `hp_cur = hp_max`, consumed | `f6:$5072` |
| `$08` | diamond: `hp_max += 8`, `hp_cur = hp_max` | `f6:$520F` |

Picking up a potion you already hold auto-uses the old one and leaves the count
at 1 (`f6:$5226`, `f6:$524B`) — the behaviour the manual describes.

`TerrainDispatch` (`f6:$5776`) switches on the terrain code under the player:

| code | handler |
|---|---|
| `$A0` | **healing well** — `hp_cur += 1` per tick, clamped to `hp_max` (`f6:$57A7`) |
| `$8C`, `$8E`, `$8F` | other terrain |
| `$EF` | destroyed with item `$05` → sets `win_flag` |
| `>= $F0` | handled at `f6:$5810` |

The well adds a single point at a time and never writes `hp_max`, which is why it
refills the bar but never extends it. Only diamonds and the bank-5 sequence
reward do that.

### A debug hook

`b0:$BDC2` is called from `$A31F` only while the console **PAUSE** switch is held
(`SWCHB` bit 3 clear). It reads the buttons directly (bit 7 set = pressed) and requires **INPT1 held
with INPT0, INPT2 and INPT3 all released**; it then steps `dbg_step` (`$1FDC`)
and waits for release. Once `dbg_step` reaches 4 it grants +8 `hp_max` and full
blood purity, then resets the counter.

It cannot get there. Steps 0 and 3 take the button-reading path, but steps 1 and
2 branch unconditionally to `$BDFA`, which runs off the end of the routine into
`$BE00` — sound-effect data. Every wrong path (`$BE00`, `$BE0E`, `$BE13`) reaches
a `BRK` within a few bytes, and the IRQ vector is `$FF00`, the reset entry, so
the console soft-resets rather than hanging. Leftover debug code.

## Map format

The world is 160 x 800 units, wrapped into a **10 x 100 grid** — one cell per 16
units of X and 8 units of Y. The grid lives in RAM as ten 100-byte column strips
based at `$2400`, `$2464`, `$24C8` … `$2784`, addressed through the tables at
`$D281`/`$D28E`.

`MapTileAt` (`f7:$D23A`, slot 9 of the bank-7 service table) resolves a position:

```
in:  Y = world X, X = world Y low, A = world Y high
out: A = terrain code, 0 when out of bounds

strip   = tbl_MapStrip[worldX >> 4]
cell    = strip[worldY >> 3]
terrain = area_ptr[cell >> 1]
```

So the grid stores an index — doubled — into the per-area property table that
`area_ptr` (`$C0`/`$C1`) points at in bank 7, `$DA00`-`$DCFF`. World X above
`$A0` wraps by subtracting `$10` from X and adding 7 to Y.

`CheckTerrainUnderPlayer` (`f6:$55E3`) feeds the player position in. Terrain 0 is
empty; anything with bit 7 set is latched into `pending_terrain` (`$CB`) and acted
on later by `HandlePendingTerrain` (`f6:$567E`) — which is where the terrain
codes in the previous section are dispatched.

### The area builder

`BuildArea` (`b3:$8000`) unpacks an area. It walks a record stream through
`src_ptr`, five bytes per record:

| lead byte | meaning |
|---|---|
| `$80` | the next two bytes are a new `src_ptr` — follow it |
| `$FE` | clear the `$93` flag |
| `$FF` | end of stream |
| other | compare against `$46`; on a match copy the next four bytes to `build_dst`, otherwise skip the record |

`build_pass` (`$90`) selects which of **two parallel display structures** is
built, via `tbl_BuildDst` (`b3:$81C5`):

| pass | list data | pointer table |
|---|---|---|
| 0 | `$2200` | `$1800` |
| 1 | `$2400` | `$1B00` |

Each row's slot in the pointer table comes from `tbl_RowDLLOffset` (`b3:$8222`)
and the offsets step by **3** — MARIA display-list-list entry size. So both
passes build display structures, not one display and one collision map.

The game is **double buffered**: `FlipDisplayBuffer` (`b3:$8276`) waits on
`MSTAT` for the end of the visible field, points `DPPH` at `$18` or `$1B`, and
toggles `build_pass` so the next build fills the other buffer.

### Resolved: the character map *is* the terrain grid

Confirmed in MAME 0.287 by running the cartridge and dumping memory. The live
display list at `$2200` holds MARIA 5-byte headers whose data pointers are
exactly the strip bases, with the **indirect (character map) bit set** in byte 1:

```
00 60 24 2B 00   -> data $2400, indirect, write mode 1, palette 1, width 21
64 60 24 0B 00   -> data $2464, indirect, write mode 1, palette 0, width 21
C8 60 24 2B 00   -> data $24C8, ...
```

And the live bytes at `$2400` are **all even and all below `$80`** — exactly the
doubled indices `MapTileAt` expects.

So the same bytes serve both roles at once. Each byte is the character number
MARIA draws for that cell, *and* `byte >> 1` is the index into the per-area
terrain table that decides whether you can walk there. There is no separate map:
the display list points at the grid in indirect mode, so one structure serves
both purposes.

The five visible entries all sit at `hpos $00` with width 21, stacked vertically,
so a strip is a horizontal band 100 cells long with 21 visible. The 16-bit
coordinate (`$5B`/`$5C`) is therefore the long scrolling axis and `$5D` the short
one.

## Darkness and the lantern

Established by replaying a recorded session in MAME and sampling the zone
palette shadow (`$1ECC`, 4 bytes per zone) every 30 frames.

`FadeToBlack` (`b3:$85FC`) ramps every zone palette down to `$00`, writing both
the shadow and the live MARIA register, and every area transition runs it. A lit
area then ramps back up over roughly 60 frames:

```
entering a lit area      $00 00 00 00 -> $00 01 11 11 -> $00 02 13 11
entering the cave        $00 00 00 00 -> stays $00 indefinitely
```

So darkness is not a separate rendering path. The character map, display lists
and collision keep running normally — the player moves, enemies still reach and
kill them — but every palette entry is black, so nothing is drawn visibly.

### The lantern is item `$09`

Counting non-zero bytes in the 44-byte zone palette block across three recorded
playthroughs:

| situation | non-zero palette bytes |
|---|---|
| lit outdoor area | 34 of 44 |
| cave **without** the lantern | **4** of 44 |
| cave **with** the lantern | 34 of 44 |

Those 4 are zone 10, the status bar, which stays lit while zones 0-9 are `$00`.

The controlled case is the third run: it entered the cave carrying item `$09`
with `boss_flags` still `$00`, and the cave lit normally. So the gate is the
lantern, not boss progress. Runs where both were true cannot separate the two;
this one holds `boss_flags` at zero and isolates the lamp.

### The mechanism, end to end

1. `LoadAreaHeader` (`f7:$F00C`) reads the area's darkness byte from the area
   stream into `area_is_dark` (`$1EC5`).
2. `f7:$F021` — **the lantern check**: if `cnt_lantern` (`$1F46`) is non-zero,
   `area_is_dark` is forced to `$00`. That is the entire test; nothing else
   consults the lantern.
3. `InstallAreaPalette` (`f7:$F12B`) copies 40 palette bytes from the area
   descriptor into `pal_target` (`$1EF8`), which the ramp walks the live shadow
   (`$1ECC`) toward. When `area_is_dark` is set each byte passes through
   `AND #$08 : LSR : LSR`, collapsing every colour to `$02` or `$00`.

The status bar lives in zone 10 and is written by a different path, which is why
it stays readable while the play area is invisible.

### Item indices observed

From the same recording, pickup order against a known route:

| frame | slot | route position | likely item |
|---|---|---|---|
| 810 | `$07` | early | blue potion (matches the static reading) |
| 1020 | `$06` | early | red potion (matches the static reading) |
| 2280 | `$0C` | mansion | knife |
| `$09` | pumpkin field | **lantern** (confirmed) |
| 4740 | `$01` | after the mansion | cross |
| 9480 | `$0D` | cabin, last before the cave | axe |

The `$06`/`$07` rows corroborate the potion identification derived earlier from
`UseSelectedItem`; the other three are inferred from route order and should be
treated as provisional.

## Confirmed by emulation

A recorded play session (57,263 frames) replayed headlessly, sampling RAM every
30 frames, checks several things derived statically:

| prediction | observed |
|---|---|
| diamond (item `$08`) gives `hp_max += 8` | three pickups: `$27`→`$2F`, `$2F`→`$37`, `$47`→`$4F` |
| boss sequence gives `hp_max += $10` | `mode_flag` 0→2 on entry, 2→0 on completion with `$37`→`$47` |
| blue potion (`$07`) sets `hp_cur = hp_max` | used at full effect, `$4F`/`$4F` |
| revive needs `hp_max >= $30` | latched at `hp_max $4F`; never latched at `$27` |
| revive sets `hp_max = ((old >> 1) & $F8) \| $07` | `$4F` → `$27` exactly |

The second death is the clean negative control: with `hp_max` back at `$27`
(39, below the 48 threshold) `revive_ok` stayed zero, no resurrection happened,
and the run ended. The mechanic is self-limiting exactly as the code implies.

Item `$08` as the diamond is now empirical rather than inferred, and `$06`/`$07`
as the two potions are confirmed by observing their use.

**Not found:** the flags that gate item spawning. The session included a blaster
that refused to appear, which is consistent with ordering-dependent spawn
conditions, but nothing in `$1E9E`-`$1EC8` settled in a way that identifies them
— those bytes are actor state, not progress flags.

### Ghosts: the only thing that lowers maximum health

`CheckGhostTouch` (`f6:$5856`) watches two dedicated actor slots — positions at
`$1EAD`/`$1EAF` and `$1EAE`/`$1EB0`, active flags at `$1EB3`/`$1EB4` tested
through bit 7. A hit runs the drain:

- sets a **40-frame cooldown** (`terrain_timer`), so sustained contact drains at
  most once every 40 frames
- refuses if `hp_max < $11` — a **floor of 17**, so ghosts can never drain you to
  nothing
- blanks one health-bar cell at `$23E7 + (hp_max >> 3)`, then `hp_max -= 8`, then
  clamps `hp_cur`

Having their own slots rather than entries in the general enemy array fits these
being the ghosts the hint at `$BA6D` warns about, which appear in only a couple
of places. This is the sole counterweight to the diamond (+8) and boss (+$10)
increases.

## Actors

Eight slots, six parallel zero-page arrays of stride 8:

| base | field |
|---|---|
| `$8F` / `$97` | position, long and cross axis |
| `$9F` / `$A7` | velocity, long and cross axis |
| `$AF` | mode: `$00` empty, `$01-$7F` death countdown, `$80-$FF` live behaviour selector |
| `$B7` | **animation counter**, incremented every frame |

`$B7` does three jobs from one counter. `f6:$5C13` takes `(B7 >> 1) & 3` as the
index into the sprite frame table, so the artwork changes every other frame.
`f6:$5C37` shifts it and branches on carry to skip the cross-axis step, so
vertical movement runs at half the horizontal rate. And `f6:$5DBD` uses
`(B7 * 4)` to index `dat_DD00` for a per-frame vertical wobble -- the drifting
motion of the flying actors.

`actor_slot_to_disp` (`$1FDE,X`) maps a slot to a display index, selecting into a
second bank of arrays the display builder consumes: `$1DF8` active, `$1E08` and
`$1E18` position, `$1E28` graphic.

`ActorMoveAndAnimate` (`f6:$6040`) advances one actor: it picks an animation
frame from a four-entry table using `tick_slow & 3`, adds `world_drift` (`$8E`)
plus the actor's own velocity to its position — so scrolling is folded into actor
motion rather than applied as a separate pass — and despawns the actor once it
leaves range.

Ghosts are the exception: they sit in their own dedicated slots rather than this
array (see above).

### Contact damage and the cross

`ActorTouchesPlayer` (`f6:$5F8A`) does a bounding-box test against the player,
then drains **blood purity** through `$D039` with a two-tier item check:

| state of item `$01` | result |
|---|---|
| selected | no damage at all |
| owned but not selected | one damage call instead of two — half |
| not owned | two damage calls — full |

`$D039` is `DrainBloodPurity` and does nothing else, so every caller of it is a
blood source rather than a health source. It also honours item `$04`
(`cnt_heart`), which grants outright immunity to blood loss — matching the
Heart's described role. Health damage runs through a separate path.

That two-tier behaviour is what identifies item `$01` as the **cross**, by
mechanism rather than by route order. A `$14` cooldown then rate-limits repeat
contact.

### There is no enemy health

`ActorDispatch` (`f6:$5BCC`) shows `actor_mode` (`$AF,X`) is a mode field rather
than a hit-point count. `$00` is an empty slot; `$01`-`$7F` is a death-animation
countdown that indexes `tbl_DeathFrames` and decrements to zero, at which point
the actor leaves the display; `$80`-`$FF` is a live actor whose value picks its
behaviour routine.

Nothing anywhere subtracts damage from an actor. A kill is simply a small
positive number written into `actor_mode`, flipping the actor out of its
behaviour and into a death animation — so **every kill is a one-hit kill by
construction**. Enemies a weapon cannot kill only flash and continue, because
their behaviour was never replaced.

Walking off the play area is a different path entirely: `ActorMoveAndAnimate`
clears `actor_mode` and `disp_active` at `$607B` without any death animation, so
an enemy can vanish having never been killed.

`ProjectileVsActors` (`f6:$5D5C`) decides kills, and `actor_mode` is both the
behaviour selector **and** the toughness counter:

```
CMP #$A0
BCS kill                ; already >= $A0 -> dies now
ADC weapon_level        ; a hit adds the weapon level
STA actor_mode,X
CMP #$A0
BCS kill                ; crossed $A0 -> dies
```

| weapon | level | added per hit |
|---|---|---|
| knife | 0 | **nothing** |
| axe | 1 | +1 |
| blaster | 2 | +2 |
| mega blaster | 3 | +3 |

Death is reaching `$A0`. Enemies that sit at `$FE`/`$FF` are already past it and
die to any hit — crows, bats and wolves, including to the knife's zero damage.
An enemy starting at `$80` needs 32 points: 32 axe hits, 16 blaster hits, and
never with the knife. Non-fatal hits set `actor_flash_timer` to `$1E`, which is
why an enemy the knife cannot kill still flickers on every hit.

### Boss fights lock the firing direction

`FireWeapon` branches on `mode_flag`. In ordinary play the projectile direction
comes from the player's facing; in a boss fight it is replaced by
`boss_fire_dir` (`$1EA9`), a constant the bank-5 sequence writes at `$B076`:

```
LDY mode_flag
BEQ normal                 ; normal: direction from player facing
LDA weapon_level
ASL A : ASL A
ADC boss_fire_dir          ; boss fight: fixed direction
normal:
STA proj_type,X
```

So the player cannot aim during a boss fight — each boss pins firing to one
direction, which is why the ram and Dr. Evil are fought shooting upward and the
skull boss shooting left, with each boss's own projectiles travelling along the
matching axis.

### Health damage, and what the cross really does

`DamageHealth` (`f7:$D402`, vector `$D036`) takes an amount in A:

```
LDA itm_cross ($1F3E)
BEQ full
  LSR A                ; carrying the cross HALVES the damage
full:
hp_cur -= A            ; clamped at zero, not wrapped
```

The cross is the game's damage-reduction item, and it applies to **every** health
source rather than one enemy type. Together with its two effects in the contact
handler it does three separate jobs:

| state | effect |
|---|---|
| selected | immune to contact blood loss |
| owned | contact blood loss halved |
| owned | **all health damage halved** |

That makes it by some distance the most valuable item in the game, and nothing in
the manual says so.

### Bosses are a third model

`BossVsProjectiles` (`b5:$B4D7`) shares nothing with the other two. Bank 5 never
references `sactor_damage` or `actor_mode` for boss damage.

A shot must land inside a box built from `boss_pos` (`$1E9E`) and four extents
(`$1EA4`-`$1EA7`) — the **weak spot**. Outside it, nothing happens. Inside:

```
boss_flash = $0A, sfx $10, despawn the projectile
if weapon_level == 0 -> stop        ; the knife cannot hurt a boss
if boss_health == 0   -> stop
DEC boss_health                     ; exactly one point per hit
```

So boss health **counts down** to zero, one per hit, and `weapon_level` is only a
gate — axe, blaster and mega blaster all do identical damage to a boss. That
inverts both other models, where the weapon level *is* the damage.

### Enemy toughness, exactly

`sactor_kind` (`$1E91,X`) is the enemy-kind field. On creation it seeds
`sactor_damage` from `tbl_SactorToughness` (`f6:$6433`), and since death is an
8-bit overflow, an entry `S` costs `256 - S` points:

| kind | seed | points | axe | blaster | mega |
|---|---|---|---|---|---|
| 0 | `$FC` | 4 | 4 | 2 | 2 |
| 1 | `$FE` | 2 | 2 | 1 | 1 |
| 2 | `$F9` | 7 | 7 | 4 | 3 |
| 3 | `$F4` | 12 | 12 | 6 | 4 |
| 4 | `$F8` | 8 | 8 | 4 | 3 |
| 6 | `$F1` | 15 | 15 | 8 | 5 |
| 8, 9 | `$C4` | 60 | 60 | **30** | 20 |
| 12 | `$EC` | 20 | 20 | 10 | 7 |
| 13, 14 | `$B0` | 80 | 80 | **40** | 27 |
| 15 | `$B4` | 76 | 76 | 38 | 26 |

The knife adds zero and cannot kill any of them. Creation also decrements
`sactor_def4`, so the area's definition slots double as a remaining-population
count.

### One header byte, two values

`ExpandAreaDef` (`f7:$F280`) unpacks each definition byte by nibble:

| nibble | table | values |
|---|---|---|
| high | `tbl_DefAmount` | `$00 $01 $02 $04 $08 $0C $10 $14 $1E $28 $32 $3C $46 $7F $FF` |
| low | `tbl_DefRateMask` | `$FF $7F $3F $1F $0F $07 $03 $01 $01 …` |

The caller stores the two results into consecutive slots, so each of the six
per-area definitions at `$1E6A`-`$1E75` is an **(amount, rate mask)** pair from a
single byte. The mask ladder is the usual descending AND-mask used to gate
periodic behaviour — the same shape as the throw rate mask — so the low nibble
controls how often and the high nibble how much.

### Items: pending until released

`item_type` (`$1E80`) carries the area's item, and **bit 7 marks it pending**.
A pending item has its authored position but is not drawn (`f6:$5168`) and is
not collectable; it is routed instead to the release check at `f6:$529C`, which
clears the bit with `AND #$7F` once the special-actor slots are empty.

So `$8E`, `$82`, `$88` are simply the blaster, crypt key and diamond waiting to
appear — not a separate class of object.

Item position comes from the area header too, and converts to a grid cell as
`band = (cross - $04) >> 4`, `cell = (long - $20) >> 3`. Checked against every
captured item: all 13 genuine items land on walkable ground.

### Region-specific enemies come from the area header

`f7:$F057` onward reads per-area content straight out of the area's record
stream: the item the area yields (`item_type`), **six values expanded into pairs
at `$1E6A`-`$1E75`** — the special-actor cast — and `throw_enable` (`$1FCC`),
which decides whether this area's enemies throw at all.

So "these only spawn in the caves" is not spawn logic. Each area simply lists a
different cast in its header, and a per-area flag enables throwing. Nothing is
selected at run time.

`f6:$52A4` ORs three of those definition slots together and only releases the
area's item when all are zero — it tests whether the slots are *empty*, not
whether anything was killed. That is why an enemy wandering off screen drops the
item exactly as a killed one does.

### Special actors accumulate damage and die on overflow

`ProjectileVsSpecialActors` (`f6:$6654`) runs the three projectile slots against
the four special actors, and uses a **different** model from the `$A0` one:

```
LDA sactor_damage ($1E81,X)
CLC
ADC weapon_level
BCC still_alive          ; no carry -> store, keep going
sactor_damage = $0C      ; carry out of bit 7 -> DEAD
```

Damage accumulates and death is an **8-bit overflow** — reaching `$100`. An actor
seeded with `S` needs `256 - S` points, so these are far tougher than anything in
the eight-slot array: with the blaster at +2, a seed around `$80` costs roughly
64 hits, which matches a fight lasting tens of seconds.

`weapon_level` is added exactly as for ordinary actors, so the knife (level 0)
adds nothing here either and can never kill a special actor. Hits still register
— `sactor_flash` (`$1E99,X`) is set for 10 frames — which is the flicker with no
progress.

`f6:$529E` ORs `sactor_damage` across all four slots and releases the area's item
only when every one is zero.

### Special actors reappear at random, not wrapped

`RelocateSpecialActor` (`f6:$65E7`) puts a special actor back on screen at a
random position — long axis `$48`-`$87`, cross axis `$44`-`$83` — then checks the
spot is placeable and, if not, nudges both axes by a random `-$10..+$0F` and
retries up to four times.

So an enemy that wanders off, or is left behind when the view scrolls, does not
wrap around: it is dropped at a fresh random walkable spot inside a fixed band,
which is why it so often turns up on the opposite side of the screen.

### Special actors, and enemy projectiles

Enemies that are *not* in the eight-slot actor array live in a parallel
structure indexed by X: `sactor_pos_long` (`$DD`), `sactor_pos_cross` (`$E1`),
`sactor_facing` (`$1E8D`). The projectile-throwing cave zombies are here, as are
the pumpkin-headed throwers and the ghosts. This is why searching the eight-slot
arrays never located the tough enemies.

`TryThrowProjectile` (`f6:$6085`) throws only when the player is **outside** a
box around the thrower (`|dx| >= $40` or `|dy| >= $30`) — close the distance and
it stops shooting. It falls into `SpawnEnemyProjectile`, which claims a free slot
in the ordinary actor array, seeds position from the thrower and sets
`actor_mode = $FD`, the straight-line behaviour.

Because `$FD` is above `$A0`, a single player shot destroys one. Player and enemy
projectiles annihilate each other with no special case at all — just the ordinary
damage model. Confirmed in `blaster-05`: zero `$FD` spawns before the cave at 58s,
then 33 of them through the fight, lifetimes of 1-3 seconds each.

### Enemy toughness is the spawn value

Because death is reaching `$A0`, an enemy's health *is* `$A0` minus the value it
is spawned with. Spawn sites in bank 6:

| site | spawn mode | hits to kill |
|---|---|---|
| `$5C77` | `$FF` | any one hit |
| `$5E37` | `$FE` | any one hit |
| `$60C6` | `$FD` | any one hit |
| `$5ED6` | `$98` | 8 axe / 4 blaster / never knife |

So a tougher enemy is literally one spawned with a lower number, and different
enemy kinds are different spawn constants feeding different behaviour routines.

Weapon level also sets `weapon_cooldown` (`$88`) from a table: knife `$28`,
axe `$1E`, blaster `$14`, mega blaster `$0A` — so the progression is partly a
fire-rate upgrade.

### Attack and projectiles

`FireWeapon` (`f6:$4FE2`) runs off the debounced fire button. It refuses if dead,
if an item is selected, if there is no weapon, or if `fire_timer` (`$87`) is
still counting — that timer is reloaded from `weapon_cooldown`, and is the fire
rate.

Projectiles occupy **three** slots in their own parallel arrays, separate from
the actor arrays:

| base | field |
|---|---|
| `$74` / `$77` | position, long and cross |
| `$7A` | type = `weapon_level * 4 + direction` |
| `$83` | graphic, from `tbl_ProjGfx` — the weapon's own icon |
| `$7D` | **animation phase**, counting down |
| `$80` | **the resolved graphic for this frame**, and the liveness flag |

`$7D` counts down on alternate frames (`f6:$4F29`, gated on `frame_ctr`) and
reloads from `proj_gfx` when it passes zero, so it is the phase of the
projectile's spin. `$80` is then computed as
`dat_4FAE[dat_4F9E[type] + $7D]` and is what the display loop actually reads:
`f6:$4F08` loads it, and a zero means the slot is empty and is skipped. Killing
a projectile at `f6:$4F52` sets `proj_type` to `$FF` **and** clears `$80`, so
the graphic doubles as the liveness test.

So weapon level never touches an enemy directly: it selects a projectile type,
and the projectile carries the weapon's identity into the collision.

### How rooms connect

There is no exit table, because screens are not nodes in a graph.
`screen_idx` (`$56`) together with `world_pos_hi` (`$57`) is a **16-bit world
position** along the long axis, and a screen number is an arithmetic slice of it
(`f6:$4B6A`):

| case | position |
|---|---|
| positive index | `(index * 8) + $20` |
| negative index | `map_limit - offset` (offset `$01`, or `$4A` when the index is `$FE`) |

The negative case is the map edge: walking off one end sets the position to
`map_limit` minus a small offset, placing the player at the opposite extreme.

And the relationship runs both ways — at `f6:$53C3` the screen index is
overwritten directly from the player's coordinates:

```
screen_idx   = player_x_lo
world_pos_hi = player_x_hi
```

So "which room am I in" is never stored or looked up; it is read off the player's
position every step. **Adjacency is implicit in the coordinate system**, which is
why no link table exists to be found.

### Which enemy a screen gets

`PickSactorKind` (`f6:$6741`) reads `tbl_ScreenKind` (80 entries, indexed by
`$8A`). A positive entry pins one kind; a negative entry is a random spec whose
low three bits are a mask, so `$F3` draws kinds 0-3 and `$F7`/`$FF` draw 0-7.

So regional variety is three tables working together: the area header says how
many and how often, this one says which kind, and `tbl_SactorToughness` turns the
kind into hit points.

### Score

`AddScore` (`f7:$D2FB`, vector `$D030`) keeps the score as **seven unpacked
decimal digits** at `$27E8`, one digit per byte, adding the value in A to the
lowest digit and propagating carries by repeated subtraction of 10. Callers pass
small constants — `$02`, `$08`, `$0A`, `$14`, `$32`, `$50` — at kills and pickups.

The address is a useful cross-check: the terrain grid runs `$2400`-`$27E7`, so the
score sits immediately above it, independently confirming the grid extent derived
from `MapTileAt`.

### The enemy AI

`SetActorVelocity` (`f6:$5D1F`) is the entire thing. It homes toward the target
coordinates in `$40`/`$41`:

```
vel_long  = (pos_long  < target) ? +1 : -1
vel_cross = (pos_cross < target) ? +1 : -1
```

then randomises by masking one axis away:

```
Y = Random & 3
vel_cross &= [$FF $FF $FF $00][Y]
vel_long  &= [$FF $FF $00 $FF][Y]
```

Half the time both axes survive and the enemy charges diagonally; a quarter of
the time it moves only across, a quarter only along. The direction is **never**
away from the player, so an enemy always converges — the randomness only chooses
how directly. That is the whole shambling-but-inevitable approach: eight bytes of
table and one random number, no state machine and no pathfinding. The movement substrate is clear;
the behaviour selection on top of it is not.

## Progression gating

`boss_flags` (`$1FBC`) is the progression bitfield. It is cleared at startup and
only ever gains bits, in one place: on completing a boss the bank-5 sequence does
`boss_flags |= tbl_BossBit[mode_flag]` (`b5:$B655`) before clearing `mode_flag`.

**Only three bits exist, one per boss** — every test in the ROM masks with `$01`,
`$02` or `$04`:

| `mode_flag` | boss | bit | unlocks |
|---|---|---|---|
| `$02` | ram | `$01` | terrain `$85`/`$86`, the mansion squares |
| `$01` | skull | `$02` | tested at `f6:$5815`, `b0:$A44D` |
| `$03` | Dr. Evil | `$04` | `f7:$F231` spawns the plasmic pumpkin |

`BossDoorGate` (`f6:$5810`) is a **lock-out**: each boss door works until that
boss is beaten, then stops responding, so you cannot re-enter a cleared arena.

The pumpkin spawn is the drop on Dr. Evil's death: with bit 2 set and the pumpkin
not yet held, `item_type` becomes `$05`.

Two terrain events consult it (`f6:$56DE`):

| terrain | behaviour |
|---|---|
| `$85` | with item `$02` selected → `forced_msg $81`; otherwise needs `boss_flags` bit 0, else draws glyph `$38` and refuses |
| `$86` | needs `boss_flags` bit 0, else draws glyph `$39` and refuses. When open → `forced_msg $82` |

`forced_msg` (`$1F9E`) is turned by `GrampaPickMessage` into message index
`(forced_msg & $7F) | $20`, so `$80`/`$81`/`$82` select story screens `$20`/`$21`/`$22`
— the three monster backstories.

So the ordering is enforced by terrain squares that silently do nothing until the
relevant boss is dead. Reported from play and consistent with the code: entering
the mansion basement by the back route bypasses the gated square, so the story
never fires and the blaster never spawns; walking back out and in through the
gate fired story `$22` and the sequence then ran normally.

## Credits

The credits are in the second text framing at `f6:$73F7`, shown across the run of
screens before the final boss:

- Produced by **Radioactive Software**
- Copyright 1990 Atari Corp
- Program and design — **Peter Adams**
- Stories — **Tammy Moore**
- Music and sound — **Paul Webb**
- Art — **Les Pardue**
- Special thanks — Adam Clayton and Rich Robbins

Grampa's message `$00` in bank 0 is an in-joke about the programmer: *"IT'S A
WONDER PETER EVER GOT THIS PROGRAM BEDUGGED!"*

## Accuracy notes

- Everything above is derived from code that reassembles byte-identically.
- Traced-as-code coverage is 54% of bank 6 and less elsewhere; the rest is data.
  The gaps are tables and graphics rather than missed code. The
  `CODE? (untraced)` labels in `MEMORY_MAP.md` are the classifier guessing, and
  in banks 1/2/4 they are false positives.
- The tracer resolves bank switches by following `LDA #n / STA $8000`. Where the
  bank comes from a table or a shadow it is pinned by hand in `annotations.json`
  (`banksw`, `bankat`) — those are stated assumptions, not deductions. One,
  `f7:$F181`, is a genuine table-driven switch forked across banks 1-4.
- The `.w` suffix in the listings forces absolute encoding where a zero-page
  form also exists; without it the round trip would not be byte-exact.
- Colours in `build/gfx/` are rendered as grey levels by pixel index. The
  `--palette` option applies an *approximate* NTSC table for previewing only.

## Room exits: two mechanisms

`screen_kind_idx` (`$8A`) has exactly one writer, `f6:$4B65`, fed from `$89`.
So every room transition passes through `$89`, and finding its writers finds
every exit in the game.

### 1. Hardcoded terrain events (fully traced)

Each event value loads `A` = destination kind, `X` = screen index, `Y` = cross
position, then calls `sub_5789`:

| event | destination | gate |
|---|---|---|
| `$81` | kind `$2B` | none |
| `$82` | kind `$14` | a weapon must be selected (`weapon_level` positive) |
| `$83` | kind `$15` | none |
| `$84` | kind `$16` | `weapon_level` > 0 |
| `$86` | kind `$1C` | `boss_flags` bit 0 SET, no item selected, weapon > 0 |
| `$90` | kind `$36`, or `$16` if already in `$36` | none |

This is where `$14` comes from -- it is reachable, but only by stepping on an
`$82` square while holding a selected weapon, which is easy to walk over
without noticing.

### 2. Per-area exit tables (parsed offline, validated)

`$8C` takes its destination from `$1F20`; `$8F` from a table at `$1F22` indexed
by X. Both are loaded by `LoadAreaHeader` (`f7:$F00C`) from the area header.

**Header pointer table: `$F32A + 2*kind`, in bank 7.** The exit section starts
at offset **24** into the header: a `$00`-terminated list of event ids, then
that many destination kinds, then that many screen indices, then that many
cross positions.

Validated against the running machine for **37 of 37** areas -- ids and
destinations both exact. 77 areas carry a header, kinds `$01`-`$54`.

Capture timing matters here: sampling `$1F20`-`$1F30` on the frame
`screen_kind_idx` changes reads the *next* room's header, which has already been
loaded. The sample must be taken about 30 frames after the index settles.

#### The index is the player's position, not a state

`sub_5963` (`f6:$5963`) derives X from `screen_idx` and `world_pos_hi` -- the
long-axis world position. So several entries can share one event id and differ
only in where along the room you trigger it. Area `$47` is the clearest case:

    id $23 -> $4B      id $25 -> $00
    id $24 -> $4C      id $24 -> $4D      id $24 -> $4E

One door, three destinations, chosen by how far along `$47` you stand. This is
the same mechanism observed in play in the pumpkin field, and it is why
`(room, edge, segment)` -- not `(room, edge)` -- is what determines where an
exit leads.

#### Reachability of the unvisited kinds

| kind | inbound |
|---|---|
| `$14` | terrain event `$82`, gated on a selected weapon |
| `$4D`, `$4E` | area `$47`, event id `$24`, from two positions other than the one that yields `$4C` |
| `$3D`, `$3E`, `$3F` | no event-based entrance in any header |

#### The room set is complete: 76 rooms

Indexing the pointer table over the whole kind range and checking where each
entry actually points settles it:

| kinds | pointer | verdict |
|---|---|---|
| 76 kinds | into the header data region (`$F3CA`+) | **real rooms -- all 76 visited** |
| `$00`, `$3D`-`$3F`, `$50`-`$53`, `$55`-`$5F` | `$0000` | no header; not rooms |
| `$54` | `$F100`, inside `LoadAreaHeader`'s own code | stale entry; parses to 24 nonsense exits |

So `$3D`-`$3F` are not unreachable rooms -- they do not exist. `screen_kind_idx`
is not contiguous over its observed range; the numbering simply has gaps.
Beating Dr Evil does not open them either: a victory run reached `$3C` and
collected item `$05`, which only spawns with `boss_flags` bit 2 set, and the
three stayed absent.

`$14`, `$4D` and `$4E` were real and were reached exactly where the exit tables
predicted -- `$14` through terrain `$82` with a weapon selected, `$4D`/`$4E`
through the third and fourth `$8F` alcoves in `$47`.

#### The plasmic pumpkin is the only code-placed item

`f7:$F22B`, run as each room loads:

    room being entered == $3C
    AND boss_flags bit 2 (Dr Evil down)
    AND itm_pumpkin == 0
      -> item_type = $05

Every other item comes from its area header. This one is authored in code,
which is why that room yields a potion before the fight and the pumpkin after.

## Terrain generates from the ROM alone

`tools/mapgen.py --offline` rebuilds every room's terrain with no emulator.

The fill at `f7:$F243` is a plain table copy whose inputs come straight from the
area header -- the same `$00`-terminated list at header offset 24 that carries
the exits:

    n   = $1EC6                  slice count
    sel = $1EC7 + x              per-slice source selector
    src = tbl_F2B4[sel] | tbl_F2E8[sel] << 8
    dst = $2400 + tbl_F31D[x]

**All 76 rooms reproduce byte-exact** against captured memory, within each
room's declared extent.

Two rooms (`$17`, `$1C`) appear to fail if you compare the whole 1000-byte
buffer, because the fill writes only `n` slices and leaves the remainder holding
whatever the previous area left there. `$17` declares 3 slices and the captured
buffer differs only in slices 3 and 4; `$1C` declares 4 and differs only in
slice 5. Compare within `n * 20` columns and both match.

### A slice is a scroll segment

The same list drives terrain and exits, and that is not a coincidence. A slice
is 20 cells wide, and a cell is 8 world units, so a slice spans **160** units --
exactly the divisor `sub_D190` uses when `sub_5963` turns the player's world
position into the index for the `$1F22` destination table.

So `(room, edge, segment)` was never an empirical approximation. The segment
*is* the terrain slice, and each slice carries its own selector, destination
kind, arrival screen and arrival cross position.

## Item numbers

Inventory slot *n* lives at `$1F3D + n`. This is the complete list as far as it
is known; the numbering is not arbitrary, the four weapons run consecutively.

| item | number | found in | how it was identified |
|---|---|---|---|
| cross | `$01` | `$14`, the church | two-tier check in the contact handler |
| **crypt key** | `$02` | `$4A`, mansion upstairs | play; matches Grampa's "the key to the crypt can be found in the upstairs of the mansion" |
| necklace | `$03` | `$12`, the shipwreck | `sel_item == $03` gates the water walk at `f7:$D0C0` |
| heart | `$04` | `$01` | `itm_heart` at the top of `DrainBloodPurity` |
| plasmic pumpkin | `$05` | `$3C`, after Dr Evil | `sel_item == $05` on terrain `$EF` is the win |
| red potion | `$06` | scattered | `UseSelectedItem`: blood purity +50 |
| blue potion | `$07` | scattered | `UseSelectedItem`: `hp_cur = hp_max` |
| diamond | `$08` | scattered | `hp_max += 8` at `f6:$520F` |
| lantern | `$09` | `$1B`, pumpkin fields | clears `area_is_dark` at `f7:$F021` |
| knife | `$0C` | `$43`, the mansion | manual: "found inside the Mansion" |
| axe | `$0D` | `$1D`, the cabin | play + manual |
| blaster | `$0E` | `$1C`, the lab | play |
| mega blaster | `$0F` | `$20`, the caverns | manual: "a dead end in the caverns" |

An item byte with bit 7 set is the same item behind that gate; `$8E` in `$1C` is
the blaster, not a different object.

### `$0B` is not an item -- it opens the top of the screen

`$0B` never enters the inventory. It rides the item mechanism to trigger a
terrain rewrite once the room is cleared. In `sub_529C` (`f6:$529C`) the release
path ORs the four `sactor_damage` bytes with `sactor_def3/4/5`; when the result
is zero -- every special actor dead and no definitions left -- the pending bit
comes off and the type is checked:

```
    LDA item_type
    AND #$7F              ; enemies cleared: drop the pending bit
    STA item_type
    CMP #$0B
    BNE L_52D0            ; any other item -> normal release
    LDY #$7F
    LDA #$6E
  L_52C5:
    STA ram_2400,Y        ; overwrite the first 128 grid cells
    DEY
    BPL L_52C5
    LDA #$00
    STA item_type         ; and nothing is ever collected
```

`$2400`-`$247F` is 128 cells: all of band 0 plus the start of band 1, which is
the top of the screen at any real play width. Grid byte `$6E` resolves through
the property table to terrain `$00`, open ground, in every table that uses it.

So killing everything in the room turns the northern rows from wall into
walkable floor, and no icon appears on the Grampa screen because `item_type` is
zeroed on the same pass. It is the only "item" in the game that changes the map
instead of the inventory.
