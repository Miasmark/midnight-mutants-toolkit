# Midnight Mutants -- NTSC and European releases compared

Two images, both 131,200 bytes (128K plus a 128-byte `.a78` header), both eight
SuperGame banks in the same order.

| | NTSC | Europe |
|---|---|---|
| md5 (whole file) | `991721cce42880a80d110901a7ecc597` | `54023876191db6ca0887fdefdc2d0bed` |
| ROM bytes differing | | **16,467 of 131,072 (12.6%)** |

The headline number is misleading. Most of it is one relocation.


## The two PAL files

Two `.a78` files carry the European dump and their cartridge data is identical
-- 0 differing bytes in all 131,072, CRC32 `7CA6D521` either way, which is the
checksum Trebor's own ROM list publishes. They differ only in the 128-byte
header:

| | ours (`Europe`) | Trebor's (`PAL`) |
|---|---|---|
| header version | 1 | 4 |
| cart type | `$0002` SuperGame | `$0012` SuperGame + **bank6@$4000** |
| bytes 64-65 | `00 00` | `01 05` |

**Trebor's is the more correct file.** The missing `bank6@$4000` bit describes
exactly the mapping the game engine lives in, `f6` at `$4000`-`$7FFF`; their
changelog lists it as a deliberate fix. MAME loads both through the same
`a78_sg` handler and they are indistinguishable in play -- same RAM hash, same
frame -- but an emulator or flash cart that honours the header may not be so
forgiving.

The NTSC pair differ only in header version and the two v4 bytes; both already
declare `$0012`.


## Nothing about the game changed

* **Banks 1, 2 and 4 are byte-identical** -- every character set and all 39
  terrain slices, which is all of the artwork the rooms are built from.
* **All 76 area headers are byte-identical** -- so every room's graphics page,
  darkness, map limit, exits on four edges, item, spawn budgets and terrain
  slice list are the same in both.
* Every gameplay constant checked at its relocated address is identical:

| | |
|---|---|
| `tbl_SactorToughness`, all 13 kinds | identical |
| weapon fire rates, all 4 | identical |
| diamond `hp_max` gain, ghost drain, floor, revival threshold | identical |
| starting health and blood purity | identical |
| special- and tough-actor contact damage | identical |
| `tbl_ScreenKind`, all 80 entries | identical |
| spawn amount and rate tables | identical |
| all three boss setup records, contact damage, victory reward | identical |
| terrain property table `$DA00` | identical |

So the two versions play the same. The differences are display timing and
colour, which is what a PAL conversion is.

## The display is taller

PAL has 312 scanlines to NTSC's 262, and the conversion spends them in the
display list list at `f6:$4277`:

| | NTSC | Europe |
|---|---|---|
| zones in the main DLL | 22 | **23** |
| scanlines | 235 | **292** |

The first three zones grow from 8, 8 and 4 scanlines to 16, 16 and 13, and one
extra zone is added -- so the added height is at the top border, above the
playfield, leaving the 10 bands of the room untouched.

The message screen's DLL at `f7:$D800` gets the same treatment, and three more
3-byte entries are added around `f7:$D1D4`.

## Which is why almost everything moved

Those inserted entries push the code after them along:

| bank | shift | cause |
|---|---|---|
| 6 | **+3** from `$42B7` | one extra 3-byte DLL entry |
| 7 | **+9** across `$D200`-`$D600` | three extra entries |

Bank 6 is a clean case to measure: of the 14,720 differing bytes, **564 are
relocation fixups** -- an address operand adjusted by exactly +3 -- and only
**19 bytes are genuinely different**. Those 19 are one loop bound in the DLL
copier at `f6:$431A` (`$7A` -> `$7F`) and a run of palette values.

The jump table at the head of bank 6 shows the relocation plainly: every target
moves three bytes, `JMP $4A2A` becoming `JMP $4A2D`.

## Colour is remapped, luminance is not

PAL's colour burst differs, so hues are shifted and brightness left alone. Of the
colour bytes sampled across banks 0, 3 and 5:

| NTSC hue | Europe hue | bytes |
|---|---|---|
| `$1` | `$2` | 35 |
| `$2` | `$3` | 13 |
| `$9` | `$B` | 2 |

**Luminance is preserved in all 50** -- only the high nibble moves. The palette
blocks in bank 7 are rewritten on the same principle, which is most of that
bank's remaining difference.

### The remap was done by eye, not by rule

Auditing the Grampa block -- the eight MARIA palettes that are live during play
-- the shift is selective rather than mechanical:

| NTSC hue | remapped | left alone |
|---|---|---|
| 0 (grey), 3 | -- | all |
| 1 | 2 | **4** |
| 2 | 3 | **3** |
| 7, 9 | all | -- |

The giveaway is `$24`: kept as `$24` in palette 1 and moved to `$34` in palette
6. The same byte, treated differently in different palettes -- so each palette
was judged on a PAL set rather than run through a formula.

One consequence is visible on the first screen. The heart draws in palette 4,
`$1A $22 $0D` in the NTSC image and `$1A $32 $0D` in the European one: only the
body colour moves, hue 2 to hue 3, and it reads noticeably pinker. Palette 4 is
shared by the crypt key, necklace, knife, axe, blaster and mega blaster, so all
of them shift with it.

### Music is not retimed

The duration and instrument tables are byte-identical and the song table differs
only by two relocated pointer bytes, so nothing about the music was adjusted for
the slower machine. It ticks once per frame, and PAL's 49.92 Hz against NTSC's
59.96 Hz makes it play at **83.3% speed** -- a sixth slower, uncompensated.

Both fixes live in the editor: rescaling `NoteDurTable` by 5/6, or a 16-byte
shim on the music entry vector that runs one extra tick every fifth frame -- 18
bytes in all, counting the two that repoint the vector at it. The shim is exact
to 0.1%, preserves every note ratio, and has been confirmed by ear on the PAL
machine with no side effects on the inventory whose spare slot it borrows for a
counter. See `EDITOR.md`.

## The signature block is gone

`$FF80`-`$FFF8` holds 121 bytes of high-entropy data in the NTSC image and is
filled with `$FF` in the European one. **No code references it** -- the only
references into that page anywhere in the listings are the reset and IRQ vectors
at `$FFFC` and `$FFFF`, and those are identical in both. This is consistent with
the console signature block, which the European image does not carry.

The vectors themselves match: NMI `$400C`, RESET `$FF00`, IRQ `$FF00`.

## Header metadata

The `.a78` header differs in seven bytes: the title text (`(NTSC)` vs `(PAL)`),
the **TV type at +57** (`$00` -> `$01`), and the **cart type at +54**
(`$12` -> `$02`). The NTSC header declares bank 6 mapped at `$4000`; the
European one does not, though the code is laid out the same way. That looks like
less accurate curator metadata rather than a difference in the cartridge.

## Both are supported

`tools/reloc.py` holds the map and the fingerprint. A cartridge is identified by
reading three constants that sit after a seam -- `tbl_SactorToughness`, the
weapon fire-rate table and the diamond's `hp_max` gain -- at both candidate
addresses; whichever placement reads the expected bytes names the release.

```
python tools/reloc.py <ntsc.a78> <other.a78>
```

reports the mapping and checks 22 landmarks through it.

`romedit.py` addresses the NTSC layout throughout and relocates its address
tables **once at load**, so every accessor is identical for both releases and
the editor's banner names the version it opened. Addresses read *out of* the ROM
-- area headers, slice pointers, palette block pointers, boss records -- are
already correct for the image and are deliberately never mapped again.

The same four edits applied to each image land where they should:

| edit | NTSC offset | Europe offset | |
|---|---|---|---|
| debug hook, 4 bytes | `$03DCA`... | `$03DCA`... | bank 0, no shift |
| axe fire rate | `$190EE` | `$190F1` | bank 6, +3 |
| toughness kind 10 | `$1A43D` | `$1A440` | bank 6, +3 |
| halve-health gate | `$1D404` | `$1D40D` | bank 7, +9 |

Reading every editable structure from both images gives identical results --
toughness, fire rates, the health ceiling, damage rules, item references,
bosses, doors, starting state, spawns, room items, terrain properties and all
114 text records. Only the palette bytes differ, which is the hue remap.

**One caveat.** Colours are still converted with the NTSC decoder, so a European
cartridge's rooms render with its remapped hues run through NTSC maths. The
palette *bytes* shown are correct; the swatches are approximate.

## Test builds for both

`tools/patch.py` identifies the layout and moves its hook and routine to match,
so a European test cartridge is made the same way as an NTSC one:

| | NTSC | Europe |
|---|---|---|
| hook, the 14-byte reset clear | `$4AE9` | `$4AEC` |
| appended routine | `$7F91` | `$7F94` |

`$7F91` holds real code in the European image -- the +3 shift pushed it there --
so the free run starts three bytes later. The patcher relocates both and refuses
outright if the bytes at the hook are not the clear sequence it expects.

## Listings for both

`src/` is the NTSC disassembly and `src-pal/` the European one, each verified to
reassemble byte-identically to its own cartridge:

```
python tools/disasm.py "<ntsc>.a78"                          -o src
python tools/disasm.py "<europe>.a78" -c annotations-pal.json -o src-pal
python tools/verify.py  "<europe>.a78" -d src-pal
```

`annotations-pal.json` is generated from `annotations.json` by putting every
address through the same map -- 176 of them move. So the European listings carry
the same labels, headers and comments as the NTSC ones, at their own addresses.
