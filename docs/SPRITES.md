# Midnight Mutants -- sprite format

How the game stores and assembles its creatures. Most of this was established by
reading the artwork against play rather than from the code alone: the ROM
reliably gives structure -- which table, which stride, which bank -- and is
consistently the wrong instrument for working out what a thing is.




## Six bytes in the wolf's row that nothing draws

`$88`-`$8D` on page `$E0` holds artwork -- 81 lit pixels, reading as a pair of
long thin legs -- and nothing references it.

The wolf's bottoms are six bytes wide and run `$8E`, `$94`, `$9A`, `$9F`, paired
with tops `$6E`, `$74`, `$7A` by composite records `$40`-`$42`. This block is
exactly one wolf-bottom slot immediately before that run, so the left half of the
`$8C` cell falls inside it while `$8E` onward is the wolf proper.

Checked two ways:

* **Statically** -- every sprite source was enumerated by finding each store to a
  graphics byte (`ram_1E28`, `ram_1E29`, `ram_1EB7`, `ram_0065`, `ram_0080`) and
  tracing the load feeding it. That gives `dat_5CE2`, `dat_5CE6`, `dat_5E6A`,
  `dat_5EF9`, `dat_6081`, `dat_6211`, `dat_6219`, `dat_6440`, `dat_6641`,
  `dat_5195`, `dat_6838`, `dat_4FAE` and the composite records. None names it.
* **In play** -- with every spawn slot filled, throwing at 1-in-2, shooting, and
  the wolf driven through all fifteen frames, the pairs drawn in that stretch are
  `$6E $74 $7A` over `$8E $94 $9A $9F`, and nothing else.

It is most consistent with a discarded wolf frame whose top no longer exists, but
it does not compose convincingly with any of the three surviving tops -- so that
is a reading rather than a finding.

Being unreferenced makes it usable. An axe projectile sprite is two bytes wide,
so `$88` is a free slot, and the editor's **fourth axe pose** mirrors `$CE` into
it to give that animation four distinct orientations instead of three.

## The spider, resolved

Page `$E0` cells `$60`, `$64` and `$68` are the spider's three walk poses -- a
body with splayed legs, the legs moving between frames. Nothing in the composite
records or any of the actor tables names them, which is what made it hard to
place; the draw is its own frame picker at `f6:$5F54`:

```
LDA ram_00B7,X : LSR A : AND #$07 : TAY : LDA dat_5EF9,Y
```

`dat_5EF9` is `$60 $60 $60 $64 $64 $68 $68 $68` -- eight bytes for eight index
values, so the mask and the table match exactly and it cannot overrun.

Confirmed by filling the start room's `def5` slot and tapping every write to the
display slots' graphics bytes: with spiders spawning, the pairs drawn are
`E0/18` and `E0/1C` for the crow and `E0/60`, `E0/64`, `E0/68` for the spider.

The spider is an ordinary actor (spawn slot `def5`, seed `$98`), so its **death**
goes through `dat_5CE6` and suffered the first-frame overrun until that was
repaired.

## The weapon shots

A projectile draws `dat_4FAE[dat_4F9E[type] + phase]`, the phase counting down
from `dat_4FD2[type]` -- which is a **frame count**, not a graphic. Type is
`weapon_level * 4 + facing`, so the three tables give every weapon's animation:

| weapon | frames | cells |
|---|---|---|
| knife | 6 per facing | `$AC $AE $B0 $B2 $B4 $B6 $B8 $BA` |
| **axe** | **1** | `$CE` up, `$BC` down and right, `$BE` left |
| blaster | 4 | `$A0 $A2` |
| mega blaster | 4 | `$A4 $A6` |

The axe is the only weapon that never animates -- one sprite for its whole
flight, which is why it appears to slide rather than turn over. The step gate
is `LDA $44 / LSR / BCC`, and `$44` counts every frame, so a step lasts two.

Every entry in `dat_4FAE` is reached by some type; none of the *table* is
orphaned. **The artwork is another matter.** The mega blaster asks for four
phases and its run reads `$A4 $A6 $A4 $A6` -- two pictures shown twice -- while
`$A8` and `$AA` hold two more frames of the same glowing orb, 65 and 74 lit
pixels, the bright core in a different place. Nothing on page `$E0` names them:
not the projectile tables, not any composite record, not either icon table.

`dat_6440` does contain those two values, which is what makes them easy to miss,
but that table feeds the special-actor slot and `f6:$65B1` gives that slot page
`$C0` -- a different page and different artwork. Page-aware, `$A8` and `$AA` on
`$E0` are unreferenced.

So the mega blaster's animation **was drawn and never wired**. Pointing its last
two phases at those cells costs two bytes.

### Two corrections to the cell labels

`$A0`-`$A6` were captioned as wolf death frames. They are the blaster and
mega-blaster shots. The wolf is drawn from composite records `$40`-`$4E`, which
name `$6E $74 $7A` and `$8E $94 $9A $9F` for its body and `$E0`-`$EA` for its
death -- so the cells at `$E0` that were marked "melting death animation?" are
the wolf, sharing `$E8`/`$EA` with the special-actor melt at records `$64`/`$65`.

`$CE` is not a decorative inverted axe on the win screen; it is the axe
projectile facing up. `$A8`/`$AA` are named by nothing on this page -- they are
the mega blaster's unused third and fourth frames, above.

### Grampa's legs straddle a cell boundary

The cell either side of that axe was labelled inconsistently for a while -- one
source calling the left half of `$CC` Grampa's legs, another calling it unused.
The pixels settle it. Reading `$C8`-`$CF` down the sixteen lines:

| bytes | what is there |
|---|---|
| `$C8`-`$C9` | a single thin column, 7 lit pixels -- the speech bubble's edge |
| `$CA` | blank |
| `$CB` | a full-height bar |
| `$CC` | a second full-height bar, flush against the first |
| `$CD` | blank |
| `$CE`-`$CF` | the axe, pointing up |

Two parallel full-height bars are a pair of legs, and they sit in `$CB` and
`$CC` -- the **right half of cell `$C8` and the left half of cell `$CC`**. The
artwork is not cell-aligned, which is why halves of it kept reading as empty.
Neither half is unused.

## Storage is line-planar

MARIA forms a graphics address as `(high << 8) | low`, and scanline *n* of a
zone reads page `high + n` at the same low byte. So a sprite `W` bytes wide and
`H` lines tall occupies pages `high`..`high+H-1` at bytes `low`..`low+W-1`.

**The zone offset counts DOWN.** The first scanline of a zone reads the highest
page and the last reads the base. Rendering pages in ascending order turns every
sprite upside down. The giveaway is the lettering on page `$E0`: `$D8`/`$DC`
spell GA&middot;ME and `$F8`/`$FC` spell OV&middot;ER only when flipped.

In 160x2 mode each byte is four 2-bit pixels, so one byte is 4 pixels wide.
Index 0 is transparent.

## There is no fixed sprite size

The 4-byte "cell" used by `tools/sprites.py` to lay out a contact sheet is a
display convenience, not a property of the data. Real widths in use:

| width | what |
|---|---|
| 2 bytes / 8 px | zombie heads, item icons, death fragments |
| 4 bytes / 16 px | bats, crows, spiders, torsos, the ghost |
| 6 bytes / 24 px | the wolf |
| 8 bytes | nothing observed, but the width field allows it |

**Frames need not start on a cell boundary.** The wolf's artwork begins two
bytes into `$6C` and `$8C` -- the first half of `$6C` is empty and the first half
of `$8C` belongs to the explosion before it -- and its three frames are 6 bytes
each. Any attempt to read it in 16-pixel units pulls in neighbouring artwork.

**A 16-pixel cell usually holds two 8-pixel sprites.** Twenty-seven cells on
page `$C0` are packed that way, as are the item icons on `$E0`: `$D0` is the
heart and necklace, `$D4` the cross and crypt key, `$F0` a diamond and a potion,
`$F4` the pumpkin and the lantern. The code confirms this independently --
`dat_6440` contains odd offsets like `$A2` and `$AA`, addressing the right-hand
half of a cell directly.

## Pages

| page | contents |
|---|---|
| `$C0` | the player and the zombies |
| `$E0` | ghosts, wolves, spiders, bats, crows, Grampa, the UI, the message font |

`build/_spritenames.py` carries the per-cell identifications, which cells are
split into halves, and per-half names, each tagged with where it came from: the
code, play, or both. Nothing is left tagged as a guess -- the last of those was
`$28`, resolved through `dat_455C` above.

## A creature is assembled from parts

A special actor occupies **two display slots**. `sub_5155` only accepts a slot
whose neighbour is also free, because it needs Y for the head and Y+1 for the
body.

### The head

    head low byte = dat_6440[direction * 16 + kind]      f6:$6440

`sub_63F5` shifts `sactor_facing` twice, but that field is already stored
multiplied by four (`f6:$6314`), so the stride is **16, not 4**. Reading it with
a stride of 4 produces a sliding window that mixes facings together and yields
four kinds where there are thirteen.

`dat_6480` at the same index gives the head's palette-and-width byte: palette in
the top three bits, width in the low five as a two's-complement count. Kind 12,
the humpback, reads 4 bytes where every other kind reads 2 -- it supplies its own
torso.

### The body

Rebuilt every frame at `f6:$638F`:

    INC ram_1E85,X          ; per-actor walk counter
    LDA ram_1E85,X
    AND #$03                ; four frames
    ADC sactor_facing,X     ; + facing, already x4
    ORA ram_00F5            ; | base from dat_67C9[kind]
    STA ram_1E29,Y          ; slot Y+1's graphics low byte

The base is `$50` for kinds 0-11 and `$70` for the humpback, giving four body
frames per facing.

That low byte does **not** address artwork directly. It indexes `dat_455C`, a
table of pointers to *composite records*:

    byte 0      the graphics page
    then groups of four, until a zero:
        palette|width, long offset, cell, cross offset

So a body is a list of parts. For a zombie it is two: a 4-byte torso from
`$C0`-`$DC` and legs from the player's own walk cycle, dropped 14 pixels. That
is why one page carries both the player and the zombies -- the legs are drawn
once and reused, and a zombie type is really just a set of heads.

**The pointer table spans banks.** Most records sit near `$48F0` in bank 6; the
humpback's are at `$D045` and up, in bank 7. Reading only bank 6 leaves that one
kind bodyless.

## Head runs are interleaved, not sequential

`$A0`-`$BC` is two cells per facing, four halves each, in a fixed order:
bignose, a spare slot, longneck, hunchback.

| facing | cells | | spare | | |
|---|---|---|---|---|---|
| right | `$A0 $A4` | bignose | headless | longneck | hunchback |
| left | `$A8 $AC` | bignose | bulb-head | longneck | hunchback |
| towards | `$B0 $B4` | bignose | pumpkin, facing away | longneck | hunchback |
| away | `$B8 $BC` | bignose | pumpkin, facing you | longneck | hunchback |

Three types carry all four facings. The spare slot is recycled for types that
need fewer: the headless and bulb-head zombies have one head apiece serving every
direction, and the pumpkin-head has two -- packed into the towards and away
groups but facing the opposite way to the group they sit in.

## Animation

**The walk** is the four body frames above, selected by a per-actor counter.

**The head bob belongs to kind 0 alone.** `sub_63E5` pushes `sactor_kind` and
`f6:$6417` pops it; a nonzero kind skips the offset. Kind 0 indexes `dat_DD00`
by `frame_ctr * 16` and shifts right five. That table is a sine sweeping `$00`
to `$FF` and back, so the offset traces a 16-frame wave from -2 to +5 pixels.
Three kinds draw the bignose zombie -- 0, 1 and 4 -- and only the first bobs.
The same table drives the flying actors' drift at `sub_5DBD`.

**The death animation** replaces the body from `dat_6641` =
`$65 $65 $64 $63 $62 $61 $60`, indexed by a decrementing counter, so play order
is `$60` through `$65`. Each frame is four 8-pixel pieces -- two torso halves and
two leg halves -- whose offsets grow (+/-3, 6, 9, 12, 15, 17), so the body comes
apart and the pieces fly outward. The first three frames split the creature's own
cells; the last two swap in fragments from `$E4`-`$EE` on page `$E0`.

Those fragments are **shared with the wolf**. Scanning every composite record for
cells `$E0`-`$EE` finds only two consumers, and both are death sequences:

| records | |
|---|---|
| `$64`, `$65` | the special actors' death -- four pieces each, two upper in palette 7 and two lower in palette 5, offsets growing from `+/-15` to `+/-25` |
| `$43`-`$4C` | the wolf's death, from `dat_5B93` -- **one** piece per frame, palette 5, at a fixed `(+6,+16)` |

So there is no use outside a death animation. The wolf does not have fragments of
its own; it borrows the actors', and uses them one at a time rather than four.

Meanwhile the head is thrown: `sub_63BF` places it at
`pos_cross + $10 - 2 * sactor_damage`, so it rises as the counter empties, with
its facing taken from `dat_63E1` = `$00 $08 $04 $0C` -- tumbling through all four
directions on the way up.

## Colour

A part's MARIA palette is the top three bits of its palette-and-width byte:
typically 7 for head and torso, 5 for legs, and 2, 4 or 6 for particular types.

* palettes 0-6 load as a 33-byte block from `b3:$81C9` into `$20`-`$40`
* palette 7 is rewritten per kind by `sub_67A3` from `dat_67E9`
* `DLI_Handler_A` reloads palettes 0 and 1 per display zone from
  `zone_pal_shadow` (`$1ECC`), so those two vary with vertical position

**Palette 6 has no fixed value.** `f6:$4C70` rewrites all three registers every
frame from the random generator:

    JSR Random : STA P6C1 : EOR #$F0 : STA P6C2 : ADC #$10 : STA P6C3

giving `c`, `c^$F0` and `(c^$F0)+$10` -- hue-contrasted at matched luminance,
which is why it strobes rather than flickering as noise. `sub_4329` forces any
part into palette 6 while its flash flag is set, and the bulb-head zombie is
authored to use it permanently.

**Palettes 2-5 are loaded twice in the whole ROM, and never per area.** A scan
of every bank for stores into `$20`-`$3F`, in both zero-page and absolute
addressing, finds direct writes only to palettes 0 and 1 (the DLI), 6 (the
random flash) and 7 (per kind). Everything else arrives through one of exactly
two block copies, which share the same loop shape -- walk X down from `$20`,
skip every fourth slot, store `block[X]` into register `$20 + X`:

| block | loaded by | when |
|---|---|---|
| `b3:$81C9` | `b3:$819E` | once, during the intro |
| `b0:$A581` | `b0:$A55B` | every time the Grampa screen opens |

**Nothing reloads them when an area is entered**, so the world keeps whichever
ran last. Since the inventory screen is opened constantly, the Grampa block is
the live one for almost all of play.

The two blocks differ, and each matches different observations:

| palette | intro block | Grampa block |
|---|---|---|
| 3 (blue potion) | gold, `$10 $00 $16` | **blue**, `$00 $94 $98` |
| 5 (red potion) | brown, `$11 $26 $20` | dark olive, `$00 $11 $14` |

So an item's colour in the world depends on screen history, not on the room.
`tools/rooms.py` renders from the Grampa block and can be pointed at the intro
block instead. The sampled values in `tools/palette.py` are kept for sprites,
where palette 7 and the per-kind table are still the governing source.

Colour bytes convert through `tools/palette.py`. Luminance comes from the luma
nibble; the hue's offset from its own grey level is then added at **constant
amplitude**, because luminance and chrominance are independent in NTSC -- a dark
colour keeps its chroma rather than fading toward black.

Two properties of that conversion are easy to get wrong and both are visible
immediately in play:

* **luminance must not be floored.** Lifting every level so that luma 0 is not
  pure black turns the two darkest entries of every palette into muddy olive --
  clearest on the bat, whose wings are luma 1 and 0 against a luma 6 gold stripe;
* **chroma must not be faded out at the bottom.** Forcing luma 0 to black for
  every hue erases every dark saturated colour in the game. The Skull's
  projectile is the clearest case: its palette is `$70 $20 $0C`, dark blue, dark
  red and white, and all three are needed for it to read as an eyeball trailing
  motion lines.

A neutral hue has no chroma offset, so hue 0 reaches black on its own without
any special case.

## A visible artwork collision

The last frame of the death animation draws the item-select reticle as the
corpse's right leg. The record at `$49EA` names `gfx $EE` at offset +22,+14, and
`$EE`-`$EF` is the same eight pixels the Grampa screen uses for the reticle.
Confirmed on screen in play.

Shared artwork is normal here -- the zombies borrow the player's legs, one sine
table serves both the head bob and the bats' drift -- but this is the only case
where the reuse is *visible*, a UI element appearing briefly as part of a corpse.

## Tools

| tool | does |
|---|---|
| `tools/sprites.py` | render cells from a page, correct vertical order |
| `tools/palette.py` | colour-byte conversion, observed overrides, the flash generator |
| `tools/animate.py` | build animation strips and the CSS that steps them |
| `build/_spritenames.py` | per-cell and per-half identifications with provenance |

## dat_455C draws almost everything

`sub_4329` is the one renderer. It takes an index, doubles it into `dat_455C`,
reads a graphics page and then a list of four-byte parts:

    byte 0            graphics page
    then, until a 0:  palette|width, long offset, cell, cross offset

Four separate investigations all ended here:

| index | what |
|---|---|
| body base + facing + walk counter | the special actors |
| `$1FC8 \| $40` | the wolf, records `$40`-`$4E` |
| `$5E` | the player: `$0D` alive, `$0E` undead holding the cross, `$10`/`$20` undead without |
| `$69` non-zero | forces every part to palette 6, which is how a struck actor strobes |

The player's undead-without-cross form is the clearest example of what the table
buys: it is a **bat** drawn from the creature page `$E0` with the bat's own cells
`$10` and `$14`, plus one extra part -- cell `$28`, a human head and shoulders in
palette 2, sitting `+3,-8` from the body. Nothing else in the game uses `$28`,
which is why it sat unidentified through the whole sprite survey. It exists to
put your head on a bat.

Anything that still looks like an unexplained sprite index is worth trying
through this table before anything else.
