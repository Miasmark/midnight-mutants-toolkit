# Midnight Mutants -- cartridge editor

A GUI for changing the cartridge itself: rooms, terrain, items, spawns and
exits, with every edit written back into a real `.a78` you can run.

```
python tools/editor.py "Midnight Mutants (NTSC) (Atari) (1990).a78"
   -> http://127.0.0.1:7800
```

It is a local server with a browser front end. Nothing leaves the machine, and
nothing is written to disk until **Save as...** is pressed -- the loaded image
lives in memory and the header shows, at all times, exactly how many bytes
differ from the file you opened.

## What it edits

| | |
|---|---|
| **terrain** | paint the 100x10 character grid with the area's own character set |
| **slice list** | repoint any segment at a different terrain slice |
| **items** | which item a room holds, and drag it to a new spot |
| **spawns** | the six placement budgets, and which creature the special slot places |
| **damage** | contact damage, stun timers, toughness seeds, and the throw rate |
| **items** | all 29 item references, the weapon fire rates, and the health ceiling |
| **bosses** | per-fight stats, contact damage, and what winning is worth |
| **properties** | what each tile *does* -- solid, door, well, hurting ground, win |
| **doors** | the scripted destinations and the conditions on them |
| **text** | all 114 script records, edited in place |
| **music** | every note of all 11 songs, with a rendered preview |
| **new game** | starting health and blood purity |
| **debug hook** | repair the unreachable PAUSE cheat |
| **tiles** | pixel-edit any character in the area bank's set |
| **sprites** | the same, for the player, creatures, item icons and Grampa |
| **colours** | every palette block in the cartridge: terrain, sprites, intro, bosses |
| **exits** | north and south per segment, plus the room's west and east |
| **room flags** | dark, and the palette block selector |

## The two rules it enforces

**Nothing may change size.** The ROM is a fixed 128K with no slack: an area
bank's window is 98% claimed by known readers, the area headers are packed end
to end, and the only free run anyone has found is 111 bytes in bank 6. So every
accessor writes in place. A slice is exactly 200 bytes or the write is refused;
a header's segment count is structural, because the `$00`-terminated slice list
sets `n` and five parallel arrays of length `n` follow it -- changing how many
entries it has would push those arrays into the next header. Values may change;
layout may not.

**Shared data is shared.** 39 terrain slices cover 76 rooms, and 23 of the 95
(bank, slice) pairs are used more than once -- `b1` slice `$2A` alone is drawn
17 times. Painting a tile edits the slice, so it repaints every other room that
draws it. The editor resolves which slice actually backs the cell you clicked,
writes it, and then names the other rooms that just changed:

> That tile lives in shared slice **$2A** -- the same bytes also draw rooms
> **$21, $22, $2B**, which changed too.

That is a property of the cartridge, not a limitation of the editor. Repointing
the segment at a different slice first (Room tab) is the way to change one room
alone -- if a suitable slice exists, since there is no room for a new one.

## Spawns

Each room carries six budgets, one byte per slot: crow, bat, wolf, ghost,
spider, and the special actor. `ExpandAreaDef` (`f7:$F280`) splits the byte --
the high nibble indexes an amount, the low nibble a rate mask. **The mask is the
reciprocal of the rate**: `$00` fires every frame, `$FF` is rare, and an amount
of `$FF` never runs out.

Two things the Actors tab flags rather than leaving you to discover:

* **`$EF` is a marker, not a count.** `LoadAreaHeader` turns it into `$22` (two,
  one chance in 64) when the player carries the cross and `$FF` (unbounded,
  every frame) when they do not. Only areas carrying it respond to the cross.
* **Kinds 10 and 11 are inert as shipped.** `tbl_SactorToughness` seeds them
  with `$00`, which the per-frame walk reads as an empty slot, so they are placed
  and ignored on the next frame. Room `$4F` asks for kind 10 and has no other
  cast, which is why it is permanently empty.

  This is fixable from the **Toughness** panel: give either kind any non-zero
  seed and it comes to life. Rooms `$46` and `$4F` already ask for kind 10, so
  one byte populates both.

The special actor's kind comes from `tbl_ScreenKind` (`f6:$6753`), one byte per
room. A positive entry pins one creature; a negative one is a mask, and the kind
is `Random AND (entry & 7)`, so the room draws from a range.

### Throwing is a rate, not a flag

Header +`$0F` loads `throw_enable` (`$1FCC`). `f6:$6325` skips the throw when the
byte is zero, and otherwise throws only when `throw_enable AND throw_rate_mask`
is zero -- so **every set bit halves the rate**. The ten throwing rooms run from
`$7F` (one in 128) down to `$3C`'s `$01`, one in two. Treating it as a checkbox
would turn `$3F` into `$01` and make a rare hazard constant.

A thrown hit costs 5 blood purity, or **9 while the necklace is held**, which
enters the drain ladder four calls early.

### Damage rules are single operands

The Actors tab also edits five constants, each the immediate operand of one
instruction:

| rule | at | stock |
|---|---|---|
| special actor contact | `f6:$6718` | `$10` |
| tough actor contact base | `f6:$5FE2` | `$02`, as `boss_flags * 2 + base` |
| tough actor stun | `f6:$5FED` | `$14` frames |
| special actor stun | `f6:$671D` | `$1E` frames |
| special actor stun, dying | `f6:$6723` | `$06` frames |

Each carries the opcode that must sit immediately before it -- `$A9` for `LDA #`,
`$69` for `ADC #` -- and the editor refuses to write if that opcode is not there,
so a rule cannot scribble into code that has moved underneath it.

### Which item grants each protection

Every item reference lives in the **Items** tab -- see below.

**Blood purity is deliberately absent.** The engine has no "drain N" argument: a
bigger loss is simply more `JSR`s in a row, so a purity cost is a count of
instructions rather than a number anything could edit.

### Toughness is global

The same panel edits `tbl_SactorToughness` (`f6:$6433`), the seed written into
`sactor_damage` when a creature is placed. Death is an 8-bit overflow, so a seed
**S** costs **256 - S** points, and a weapon lands its own level per hit: axe 1,
blaster 2, mega 3. A knife is level 0 and never kills a special actor at all.

**This table is shared by the whole game.** Changing kind 6 changes every
Pumpkin-head in every room; the panel shows how many rooms place each kind.

It is 13 bytes and the editor refuses anything past kind 12, because `dat_6440`
-- the head graphics -- begins at the next address.

## Item references

The **Items** tab gathers **every instruction in the cartridge that names one
inventory slot** -- 29 of them, grouped by the item they currently name. The
list is derived from the listings that rebuild byte-identically, so it is the
complete set rather than the ones anyone happened to look for.

| item | references | | item | references |
|---|---|---|---|---|
| cross | 7 + 1 selected | | blue potion | 3 |
| crypt key | 2 + 1 selected | | lantern | 2 |
| necklace | 2 + 1 selected | | knife / axe / blaster | 1 each |
| heart | 2 | | **diamond** | **0** |
| plasmic pumpkin | 1 + 1 selected | | **mega blaster** | **0** |
| red potion | 3 | | | |

The inventory is flat -- slot = `$1F3D + id` -- so pointing a reference at a
different item is a one- or two-byte write. Each is guarded by the opcode that
must precede it, and refuses any id outside 1-15.

Three distinctions the tab marks rather than hides:

* **`sel`** entries compare `sel_item` against an id, so they test the item
  *selected* on the Grampa screen rather than merely carried. There are four:
  the cross's contact immunity, the crypt key's terrain `$85`, the necklace's
  water walk, and the pumpkin's win condition.
* **`w`** marks a write rather than a test. Repointing one redirects where a
  count is stored, not what is read.
* **Indexed accesses are excluded.** `INC inventory,X` in `CollectItem` names
  the base of the array, not a slot; offering it as a per-item gate would be a
  lie. Six such sites exist and none appear in the list.

The diamond and the mega blaster appear nowhere because nothing reads either
slot -- both are write-only, and their effects happen elsewhere.

### The health ceiling

Five constants that are really one mechanic, plus the threshold they feed:

| what | at | stock |
|---|---|---|
| starting health | `f6:$4AE3` | `$27` |
| diamond raises `hp_max` by | `f6:$5212` | `$08` |
| ghost touch lowers `hp_max` by | `f6:$5890` | `$08` |
| floor on `hp_max` | `f6:$5880` | `$11` |
| frames between ghost drains | `f6:$587A` | `$28` |
| revival needs `hp_max` of | `f6:$4EC1` | `$30` |

The diamond is the **only** thing that raises `hp_max` and the ghost the only
thing that lowers it -- `CheckGhostTouch` is the sole reducer in the game, which
is why a long crypt fight quietly undoes diamonds. The floor means the ceiling
can never be drained to nothing.

Because the diamond's gain and the revival threshold are both editable, the tab
derives what a second life actually costs and says so as you type: two diamonds
as shipped, one at `$10`, three at `$04`, and *unreachable* at `$00`, since then
nothing raises `hp_max` at all. Blood loss stays terminal regardless.

### Weapon fire rate

The same tab edits `dat_50ED`, four bytes indexed by `weapon_level`:

| level | weapon | delay |
|---|---|---|
| 0 | knife | `$28` |
| 1 | axe | `$1E` |
| 2 | blaster | `$14` |
| 3 | mega blaster | `$0A` |

Lower is faster. This is most of what the weapon progression actually is: against
a boss every weapon removes exactly one point per hit, so the mega blaster is
better only because it lands three times as often as the axe. The table is
exactly four bytes -- `$50F1` is the next instruction -- and level 4 is refused.

## Music

All twelve song slots, three levels deep: a song holds two voice tracks, a track
holds patterns, a pattern holds two-byte notes. **1,599 notes are reachable**,
and the parse was checked note-for-note against `tools/music.py` -- every song,
both voices, identical.

    byte 0   instrument (high nibble) | duration index (low nibble)
    byte 1   waveform (top 3 bits) | frequency (low 5 bits); 0 is a rest

That second byte is the one worth understanding before editing it. `AUDF` is a
**five-bit** register: the player writes the whole byte, the chip keeps bits
0-4, and the engine shifts the same byte right by five to pick the waveform from
the three bits the chip discarded. So timbre and pitch share one byte, and the
editor masks them apart -- changing pitch leaves the waveform alone and vice
versa.

Click any note to edit its pitch, waveform, instrument and duration, or mark it
a rest. **Patterns are packed end to end**, so a note's values can change but
the count cannot: adding one would push every following pattern along.

### Hearing it

**Play** renders the current song to a WAV through the same TIA model
`tools/music.py` uses -- real polynomial counters and the actual five-stage
envelope -- and plays it in the browser. It renders from the **edited image in
memory**, not the file on disk, so a note changed a moment ago is what you hear.
Verified: editing one note of the dirge changes the rendered audio, and
reverting restores it byte-for-byte.

The renderer addresses its four tables by NTSC constant, so for a European
cartridge the editor points them at that image's copies for the duration of the
render. Both releases hold identical music data, so the two sound the same --
what differs is the machine clock, which is what the timing options below
address.

## PAL music timing

A note's duration index is a **count of frames** and `MusicTick` runs exactly
once per frame, so tempo follows the machine. The European cartridge was never
retimed -- its duration and instrument tables are byte-identical to the NTSC
ones -- so at 49.92 Hz against 59.96 Hz everything plays at **83.3% speed**.

The **rescale durations** checkbox multiplies `NoteDurTable` (16 bytes) by 5/6.
It is pure data, fully reversible, and needs no code or RAM:

| | error against the intended wall-clock length |
|---|---|
| the eight longest durations | within **1.3%** |
| the shortest two | up to 20%, but they are ornamental |
| the melody's 2:1 (16 and 8 frames) | becomes 13:7, about **7% off** |

Eight of the sixteen entries divide by 6 exactly; the rest round, and that
rounding is where the ratio drift comes from. Set against doing nothing, which
leaves every note **20% too long**, it is a clear improvement but not a perfect
one.

### The exact alternative

**extra tick, 6 per 5** installs a 16-byte shim instead -- 18 bytes in all,
counting the two that repoint the music entry vector at it -- and changes the
clock rather than the data, so every note ratio is preserved exactly:

```
$7FF0  DEC $1F47        ; the counter
$7FF3  BPL $7FFD
$7FF5  LDA #$04
$7FF7  STA $1F47
$7FFA  JSR $7712        ; the extra tick
$7FFD  JMP $7712        ; the normal one, still a tail call
```

Six ticks per five PAL frames is 59.90 Hz against NTSC's 59.958 -- **0.1% out**.

Two things make it small. `MusicTick` has **seven call sites across four banks**,
but all of them go through the single entry vector at `f6:$4009`, so redirecting
that one `JMP` covers every path with a two-byte change. And the counter uses
inventory slot `$0A` (`$1F47`), which nothing in the cartridge touches: no room
places item `$0A`, both Grampa screen loops stop at slot 7, and the two
`DEC`/`LDA inventory,X` sites index by `sel_item`, capped at 7. A write tap over
four recorded sessions saw **eight writes, all inside the first 66 frames** from
the BIOS memory test and boot, then nothing across ~11,900 frames.

The code sits in the last 16 bytes of bank 6, leaving the free run at `$7F91`
for `tools/patch.py`. That address is deliberately not relocated: it is measured
from the end of the bank, which is `$7FFF` in both releases.

**Use one or the other, not both** -- they correct the same thing twice.

**Both are refused on an NTSC cartridge.** They correct a 50 Hz machine, so
applying either to a 60 Hz one makes the music run 20% fast -- the same error in
the other direction. The checkboxes are disabled when the badge reads NTSC and
the server refuses the write regardless, so it cannot be done through the API
either. Turning them *off* stays available on any image, so a wrongly patched
cartridge can always be put back.

**Verified in play.** The shim was tested by ear on the PAL machine and the
tempo is right. The inventory was exercised across a pickup and back to confirm
the borrowed byte does not leak: slot `$0A` sits outside the range both Grampa
screen loops walk, so a counter living there draws no icon and moves no cursor.

Between the two, **prefer the shim**: it is exact, it preserves every note
ratio, and it is now the tested one. The rescale option remains for anyone who
would rather not add code to the cartridge at all.

## Water walk by terrain

Bit 2 of a terrain byte marks water. The engine never tests it -- the collision
check is only `AND #$03` -- so `$05`/`$06`/`$07` block exactly as
`$01`/`$02`/`$03` do, and the necklace crossing is a **position** test instead:
the necklace selected, room `$01`, and the player inside a fixed rectangle. The
fountain in the first room is passable and identical water in `$02`, `$03`,
`$07`, `$0F` and `$11` is not.

**read bit 2 instead** gives the bit its obvious meaning. Where the terrain has
decided to block, a 21-byte shim at `f6:$7FD0` asks two more questions:

```
$7FD0  LDA $1FA9      the original room-$01 rectangle, still honoured
       BNE allow
       LDA $4F        the terrain byte that just blocked
       AND #$04       water?
       BEQ block
       LDA $CC        sel_item
       CMP #$03       the necklace, selected rather than carried
       BNE block
allow: CLC / RTS
block: SEC / RTS
```

The call site is the one instruction it replaces -- `LDA ram_1FA9` at
`f6:$5666` becomes a `JMP` to the shim -- so the original rectangle keeps
working and nothing that used to be crossable stops being. Twenty-four bytes in
total, and unticking restores every one.

### The budget, shown in the editor

The Items tab carries a **Space for code patches** panel: a bar of how much of
the run is still contiguous, each occupant with its size and whether it is
installed, and what that leaves for a test build. Each toggle is tagged with
what it costs -- `21 b`, `16 b`, or **in place** for the ones that only change
an existing operand and cost nothing.

```
108 of 108 bytes free        stock
 60 of 108 bytes free        with the water shim installed
```

The number shown is the **largest unbroken run** anywhere in the tail, together
with the total free. Counting only from the bottom reports zero the moment the
test-build patcher takes the first byte, which makes a cartridge with 93 bytes
still free look completely full.

Most of this editor never touches it. Repairing the debug hook rewrites four
branch operands, rescaling the durations rewrites sixteen table bytes, and every
value in every other panel is an in-place byte: none of them appear in the
budget.

### A second pocket

The **compact the flip** checkbox rewrites `sub_44EC`, the display
double-buffer flip. Each branch writes ten display-list high bytes as ten
`LDA #`/`STA` pairs although the value changes only twice; loading each value
once frees **28 bytes** at `f6:$4540`, with every write unaltered.

Patches prefer that pocket, so turning it on leaves the tail of bank 6 whole
for test builds:

| | tail free | water walk | music retick |
|---|---|---|---|
| stock | 108 | -- | -- |
| water walk only | **60** | `$7FD0` | -- |
| compaction + water walk | **108** | `$4540` | -- |
| compaction + both | 92 | `$4540` | `$7FF0` |

Only one of the two fits the pocket -- 21 and 16 bytes against 28 -- so the
second falls back to the tail. Restoring the original routine is refused while
anything is installed in the pocket, since that would overwrite it.

**Tested in play**, not only built: 22,215 frames ending with the Ram boss
beaten, with the display list valid throughout, the buffers alternating 17,002
times, and no writes into the freed bytes. The stock cartridge shows the same
isolated single-frame samples during play, so those are the game's own
behaviour. Cycle count does change and the random generator mixes scratch RAM,
so a compacted cartridge takes a different random path from identical inputs --
a different game, not a broken one.

### Sharing the tail of bank 6

Three things want the free run at the end of bank 6, and they fit:

| | at | bytes |
|---|---|---|
| test-build patcher (`tools/patch.py`) | `$7F91`, `$7F94` on PAL | **4 + options, often 0** |
| water walk | `$7FD0` | 21 |
| music retick | `$7FF0` | 16 |

The patcher's routine is built per invocation, and two of the things it can set
cost nothing at all. **Starting health and blood purity are already written by
immediates the reset executes** -- `LDA #$27` into `hp_cur` and `hp_max`,
`LDA #$64` into `blood_purity` -- so `--hp` and `--purity` change those operands
and append nothing. A build asking only for those installs no hook: two bytes
differ from the stock cartridge and the reset runs unaltered.

What still needs code is the inventory and the progression flags, which want
individual stores. That routine is reached by displacing **one three-byte
instruction** on the reset path -- the lone `STA $1FD9` at `f6:$4AC8` -- which
it re-does first.

| | bytes |
|---|---|
| the displaced store | 3 |
| per item | 5 |
| boss flags | 5 |
| per zero-page value | 4 |
| `RTS` | 1 |

| build | before | now |
|---|---|---|
| health, or health and purity | 21 | **0** |
| a weapon, the lantern and a boss flag | 30 | **19** |
| every item at once | 91 | **74** |

The saving comes from where it hooks. An earlier version displaced the
**14-byte** clear sequence at `$4AE9` and had to repeat all four of its stores
before doing anything useful; hooking a single store instead spends three.

That leaves **60 bytes** between `$7F94` and the water shim on a European image
with both editor patches installed -- comfortable for anything but a
grant-everything build. `patch.py` measures the run that is actually free rather
than assuming the tail is empty, and says so plainly:

```
patch routine is 91 bytes and only 60 are free at $7F94
  $7FD0 holds something already -- an editor patch, most likely. Turn it
  off, or build the test cart first and patch it in the editor afterwards.
```

## Terrain layers on the room view

Two checkboxes above the canvas, with a legend beside them.

**Collision** tints each cell by what it does to the player. The grid holds a
character number and the property table is indexed by `(cell >> 1)`, so two
adjacent characters always share one entry:

| | |
|---|---|
| solid red | class 3, blocks everywhere |
| red half-triangle | class 1 blocks the lower right, class 2 the upper left |
| purple | a scripted tile -- bit 7, an event rather than a wall |

**Water** tints bit 2 blue.

**Exits** marks every scripted tile and labels it with where it leads, colouring
by what it is -- green for a door, red for a boss door, orange for hurting
ground, blue for the well, yellow for the win square.

Three of the sixteen events name no destination at all. They defer to the room's
own header, and the north and south tables are *per segment*, so where the tile
leads depends on which column it sits in:

| event | resolves to |
|---|---|
| `$8C` | the header's west field |
| `$8F` | `north[column / 20]` |
| `$8E` | `south[column / 20]` |

The layer does that resolution, so room `$10`'s `$8F` at column 29 reads as
segment 1 and shows `-> $41` rather than "north table". The **Exits tab** lists
the same doors in full, with their conditions -- a weapon, a selected item, a
boss beaten -- which are too long to sit on the picture. Worth remembering what that bit is: the collision
test is `AND #$03` and never looks at it, so `$05`/`$06`/`$07` block exactly as
`$01`/`$02`/`$03` do. It marks water for the authors, not for the engine, which
is why the water-walk repair had to be taught to read it.

The overlays are drawn from the room's own property table, so they follow any
edit made in the terrain-properties panel immediately.

## A room's width, in the Room tab

A header is **25 + 5n bytes**: 24 scalars, a `$00`-terminated list of n slice
ids, then four parallel n-entry exit arrays. So the segment count *is* the
room's width, and changing it resizes the record.

The records cannot grow where they sit. They are packed with nothing to spare
and **five of them deliberately overlap** -- room `$10`'s header begins three
bytes inside room `$0F`'s last exit array, sharing them, so its stream, page and
dark flag *are* the tail of the room before it. Rewriting a tail in place would
silently edit the next room.

They can move instead. Every header is found through the pointer table at
`f7:$F32A`, never by walking, so a record may live anywhere the tools accept --
and relocating one leaves its original bytes untouched, which is exactly what an
overlapping neighbour needs. Widening therefore writes the new record into free
space above the block and repoints the table; returning to the shipped count
writes it back home, edits and all, and releases the borrowed space.

**Five segments is the ceiling.** The map builder at `f7:$F243` lays each one
20 columns into a 100x10 buffer at `$2400`, so five fill it exactly. A sixth
would start at column 100 -- the second band -- and its final row would run past
`$27E7` over `score_digits`. Fourteen shipped rooms already use five, three use
four, so nothing about going past three is unusual; five is simply where the
buffer ends. Verified on hardware: a five-segment start room scrolls cleanly and
`score_digits` stays zero throughout.

**Space is not the binding constraint.** `areas.parse` only accepts a header at
`$F3CA` or above, leaving 86 bytes at `$FF24` and 30 at `$FEE2`. A five-segment
header is 50 bytes, so the larger run takes any room the engine allows.

New segments repeat the room's last slice and arrive with no vertical exits.

**Map limit** is now editable too: the base at header +3, to which the loader
adds `$AE`. It is where the east exit triggers and where the clamp at
`f6:$53A6` stops the player, so it wants to match the width.

## Disassemble

A button beside Save. It writes the edited image to a temporary cartridge, runs
`tools/disasm.py` over it with the matching annotation file -- `annotations.json`
for NTSC, `annotations-pal.json` for PAL -- and drops nine `.asm` listings in a
`(disassembly)` folder next to the cartridge you opened. It takes under a second.

Two things worth knowing. The annotations describe the **stock** layout, so code
you have added through the editor lands in a region the tracer treats as data
and comes out as `.byte` rather than instructions; the bytes are right, the
labels are not. And the disassembly is of the image *as edited*, including
unsaved changes, so it is a way to read what a patch actually did.

## The item on the room canvas

The room picture draws the item where the game puts it, using the same character
from `dat_5195` and the same palette choice the reference renderer makes --
including the strobing one for the pumpkin and the diamond, which stands in one
frame of the random palette. The old orange box and label are still available as
the **item marker** checkbox above the canvas.

## The weak spot and the portraits, in the Bosses tab

Four bytes of each setup record are the hitbox: `+2/+3` are the long-axis edges
as offsets from `boss_pos`, `+4/+5` the cross-axis edges. `BossVsProjectiles`
(`b5:$B4D7`) tests a shot against exactly those, so they *are* the weak spot.

| boss | long | cross |
|---|---|---|
| 1 Skull | `$3C`-`$44` | `$40`-`$50` |
| 2 Ram | `$50`-`$5A` | `$18`-`$24` |
| 3 Dr Evil | `$52`-`$5C` (overwritten every frame) | `$40`-`$50` |

**Everything is shown as the raw byte and its distance from stock.** Only Dr
Evil's marks can be tied to the picture from the ROM alone; the Skull's and the
Ram's portraits are narrower than the screen, so the window origin is not the
blit column and their horizontal placement on the reference page is observation
rather than derivation. Shifting what is there is meaningful; aiming at a screen
coordinate is not. Each axis has -8/-1/+1/+8 buttons that move both edges
together so the window keeps its size.

Dr Evil gets three more, because he is the only boss that moves his own hitbox:
the two window bases (`$2E` and `$66`), the width added to whichever is live
(`$0A`), and the two shot offsets (`+$34`, `+$66`). The shot leaves whichever ear
is currently weak, so a window and its shot offset want moving together.

**The portraits** are the appearance, and they are painted, not typed. There is
no arena -- the only thing blitted is the boss itself, one picture pasted into
the character map: 9x9 at `b5:$9000`, 16x9 at `$9055`, 20x10 at `$90E9`. Each
cell is a character number and `$00` is empty.

Each boss gets the same treatment a room does: the portrait is drawn from its
own character set and palette, with a cell grid over it, beside a tray of every
character in that set. Pick from the tray, then click or drag on the picture;
right-click erases to `$00`. A stroke is applied optimistically on the canvas
and sent as **one request per value**, so dragging across forty cells is a
couple of calls rather than forty.

Two details come from the way the blit works rather than from the picture:

* **Colour follows the destination band, not the portrait row.** The picture is
  pasted at (column, row) into the 100x10 map, and a character takes its
  palette from the map band it lands in. Dr Evil is ten rows tall, so he
  crosses every band and changes colour down his length -- a gradient the game
  gets for free, and one the editor has to reproduce or the preview lies.
* **The character set is per boss.** The Skull and the Ram are built from
  `CHARBASE $80`, Dr Evil from `$A0`, so his tray is a different alphabet.

The rendering was checked against `tools/arenas.py` -- the renderer that
produced the published portraits -- pixel for pixel and colour for colour on all
three, with no missing, extra or miscoloured pixels.

Their palettes remain reachable through the three boss palette sets in the
Colour tab.

### The tabs are addressable

Each panel has a hash: `#bosses` opens the Bosses tab, `#text` the Text tab, and
switching tabs keeps the hash in step. A particular panel can be linked to, and
a reload comes back to it instead of to Tiles.

## Blood purity, in the Items tab

Every loss goes through one routine that takes a single point per call, so the
cost of a hit is the number of consecutive calls -- seven runs, seventeen calls,
all listed with the number currently active. Lowering one writes `NOP`s over the
trailing calls; a call and three `NOP`s are the same three bytes, so nothing
moves and nothing needs free space.

The projectile ladder gets two extra controls, because it is the only site with
a conditional entry point:

* **without the necklace** -- the branch operand, so any value the rungs allow
* **check the necklace at all** -- unticking replaces `LDA itm_necklace` with
  `LDA #$00 / NOP`, leaving Z always set so the branch is always taken. Both
  cases then cost whatever the box above says, and the necklace's hidden
  penalty is gone. Three bytes, in place.

Verified byte-exact both ways on both releases, and a gate-off cartridge tracks
the stock one frame for frame through a recorded session. The projectile path
itself was not staged live -- see the note in ITEMS.md for why the change is
sound.

## Sound effects, in the Music tab

Two separate things, because the game separates them: **which effect each event
asks for**, and **what each effect sounds like**.

The request side is 17 sites, every one a `LDA #n` (or `LDX`) into
`sfx_request`, listed by what fires them -- the killing blow, a hit survived,
item collected, a boss hit, the well, hurting ground, special-actor contact, and
so on. Point any of them at a different id. Weapon fire is deliberately absent:
`f6:$5046` computes its id as `weapon_level + 1` rather than naming one, which
is why ids `$01`-`$04` all share a stream.

The stream side lists all 15 streams in `b0:$A085`-`$A16E` with which ids play
each -- including the three that nothing plays (see SOUND.md). A stream is
hex bytes, edited in place: `$00` ends it, a byte under `$10` sets the waveform
and costs no frame, anything else is one frame of pitch with its top four bits
as the volume. It may be shortened freely, and lengthened only over what follows
if no id points there; the editor reports how much room that is and refuses
anything that would run into a stream in use.

## The banner hold, in the Text tab

Each record's second parameter byte, shown beside its address. `sub_687E` copies
it to `ram_1E7A` and `f6:$40CF` counts that down once every 32 frames, so a step
is a little over half a second. The pickups use `$96`; `$00` means the banner
gives way as soon as anything else asks for it.

## Shimmer, in the Text tab

Each framing-B record shows a **shimmer** checkbox beside its address, with the
terminator byte it controls. `$FE` makes the banner pulse, `$FF` holds it still
-- see TEXT.md for the mask and the display interrupt that reads it. Of the 66
framing-B records, 15 shimmer as shipped, and they are almost exactly the item
pickups: four pickups end `$FF` and so sit still, which the Items tab offers as
a one-click repair (below).

Framing A records are drawn by other code and show *no shimmer* instead.

### Pickups that never shimmer

The Items tab carries a **make them shimmer** box covering the four pickup
messages that end `$FF` while everything around them ends `$FE` -- the cross
(record `$33`) and the three weapons above the knife (`$2F`, `$30`, `$31`). The
knife's own four lines shimmer, as do both potions, the crypt key, necklace,
heart, lantern and all four diamond variants, so there is no rule under which
these four should be static. Four bytes, all in bank f6, none of them near the
framing-A records that the guard below protects.

The box is refused in one situation. Records are packed end to end, so a
record's terminator is also the next record's first byte -- and while nothing
reads it as a framing-B marker, **framing A is recognised by its `$FF`**. Four
records in bank 0 end on the `$FF` that opens a framing-A record; turning
shimmer on there would hide that record, so the editor refuses and says which
address is at stake. Turning it *off* is always allowed.

## Death animations that read past their table

Two animations pick a frame by using a countdown as an index into a table, and
both are seeded one higher than the table is long. The first frame of each reads
whatever follows -- in both cases the `$A5` opcode of the next routine -- and
draws sprite `$A5`, a misaligned slice of the blaster artwork. Every later frame
is correct.

| animation | table | entries | seed | bad index | fix |
|---|---|---|---|---|---|
| crows, bats, ground enemies | `dat_5CE6` | 8 | `$08` used directly | 8 | seed `$07` |
| ghosts | `dat_6219` | 8 | `$10`, halved | 8 | seed `$0F` |

One byte each, and nothing else depends on either value: every comparison of
`actor_mode` is against `$A0`, and the four other reads of the ghost's state are
sign or zero tests. Each animation runs one tick shorter.

### The rest of the death animations are sound

Audited the same way -- table length against the widest index the code can
produce:

| animation | table | entries | widest index |
|---|---|---|---|
| special actor, body break-up | `dat_6641` | 7 | 6 (`$0C` halved) |
| special actor, head throw | `dat_63E1` | 4 | 3 (`AND #$03`) |
| moving actor (the bat's cells) | `dat_5CE2` | 4 | 3 (`AND #$03`) |
| second actor (the crow's cells) | `dat_5E6A` | 20 | 3 (`AND #$03`) |
| ghost, alive | `dat_6211` | 8 | 7 |
| special-actor heads | `dat_6440` | 64 | 27 |
| projectiles | `dat_4FAE` | 36 | 35 |

The wolf and the special-actor melt are composite records rather than sprite
tables, and both were already accounted for.

## The ghost's first death frame

A dying ghost picks its picture with

```
LDA ram_1EB3,X : LSR A : TAY : LDA dat_6219,Y
```

so the index is the state halved. The kill at `f6:$6268` seeds the state with
`$10`, and `$10 >> 1` is **8** -- but `dat_6219` holds eight entries, `$6219` to
`$6220`, and `sub_6221` begins immediately after. The first frame therefore reads
`$6221`, the `$A5` opcode of that routine, and draws sprite `$A5`.

The ghost is 16 pixels wide and drawn as a top half plus `top + $20`, so that
frame is a misaligned slice of the mega blaster's orb over a misaligned slice of
the AWESOME lettering -- visible in play as a brief flash of text. Every later
state indexes 7 or below and is correct.

**Seeding `$0F` keeps every index inside the table.** One byte. Nothing else
tests the value: the four other reads of `ram_1EB3` are sign or zero tests, so
the only other effect is that the animation runs 15 ticks instead of 16.

This is the same shape as the reticle leg -- an animation reaching one entry past
its table into whatever follows.

## The mega blaster's lost frames

It asks for four phases but its run reads `$A4 $A6 $A4 $A6` -- two pictures
shown twice. Cells `$A8` and `$AA` hold two more frames of the same glowing orb,
with the bright core in a different place, and nothing on page `$E0` names them.
The animation was drawn and never wired.

Two bytes point the last two phases at it. No new art, no trade-off, and the
phase count is already right.

## The axe never turns over

`dat_4FD2` is the projectile frame count: the knife asks for 6, both blasters
for 4, and the axe for **one**, so it shows a single sprite for its whole flight
and reads as a slide rather than a throw.

The art is already there. The axe's four entries sit together at index `$18` as
`$CE $BC $BE $BC` -- three orientations, one per facing with down and right
sharing -- so pointing every facing at that run and asking for four phases makes
it tumble, with nothing new drawn.

Two costs, both deliberate:

* **The per-facing orientation goes.** An axe thrown left tumbles like one
  thrown up. The other facings cannot keep their own window because base `$19`
  plus three phases runs off the end of the axe run into the blaster's `$A0`.
* **The step gate is shared.** It moves from `$44`, which counts every frame, to
  `$45`, which counts every other, so a pose holds four frames instead of two.
  The knife and both blasters slow with it -- which suits them; the knife's
  tumble was faster than it needed to be.

Nine bytes, all in place, reverting byte-exactly on both releases.

### And a fourth pose, using space nothing claims

With the tumble on the run reads `$CE $BC $BE $BC` -- four phases over three
drawings, so one pose shows twice. Page `$E0` has room for another: the six bytes
at `$88`-`$8D` are referenced by nothing at all (see SPRITES.md), and an axe
sprite is two bytes wide, so `$88` is a free slot.

**Give it a fourth pose** mirrors `$CE` into `$88` and points the repeated phase
there, so the axe turns through four distinct orientations. 32 bytes of artwork
plus one table byte, and the stock contents of `$88` are restored exactly on
revert.

It only shows with the tumble on -- without it the phase never leaves 0, so the
axe would still draw `$CE` for the whole flight.

## The pumpkin's missing pickup line

Every item announces itself when you pick it up, except the plasmic pumpkin --
the chain at `f6:$527A` has no link for kind 5 and falls through to the `RTS` at
`$5298`. Since the pumpkin is what ends the game, and the winning square sits in
one room of the pumpkin fields with nothing pointing at it, the silence costs the
player the only hint they were going to get.

**Add the line** writes that link. Three pieces:

| piece | where | cost |
|---|---|---|
| `JMP` over the tail | `f6:$5296`, the last `BEQ` and the `RTS` | 3, in place |
| the shim | prefers the pocket, else `f6:$7FC4` | 12 |
| the record | `f6:$7F91` | 3 + the text |
| slot `$24` repointed | `f6:$69EF` | 2, in place |

The shim is entered with Z still set from `CPX #$09` and A already `$3F`, so the
lantern's path is one taken branch; otherwise it loads `$24`, tests for kind 5,
and either shows the message or returns exactly as before.

Slot `$24` is one of five pointer-table entries no code path can reach (see
TEXT.md), so aiming it at a new record costs nothing and strands nothing.

The record ends `$FE`, not `$FF`, so the banner shimmers the way every stock
pickup does -- see TEXT.md for why the terminator is what decides that.

The line is editable: up to 48 characters on a clean cartridge, `|` breaks it,
and no single line may exceed 39 -- the widest the display fits. The record is
data rather than code, so it takes any free gap instead of a fixed home, which
lets it sit alongside the test-build patcher's routine; on a cartridge that
already carries other patches fewer characters fit, and the editor says how many
rather than failing vaguely. The default is

```
TAKE IT TO THE PUMPKIN FIELDS
AND SET ME FREE!
```

Verified two ways. Simulating the chain for every item kind on both releases
shows each existing item reaching the same message it always did, kind 5 now
reaching `$24`, and unused kinds still silent. A probe cartridge pointing the
title slot at the new record confirms it renders, both lines, in the game's font.

## The selected-item icon

The status bar shows whatever is selected, drawn by `sub_681B` from two tables
indexed by `sel_item`: graphics at `f6:$6838`, palette and width at `f6:$6845`.
Three entries are wrong, and the stock game shows it during play.

| item | at | change | why |
|---|---|---|---|
| crypt key | `$6847` | `$BE` -> `$9E` | palette 5 -> 4 |
| necklace | `$6848` | `$BE` -> `$9E` | palette 5 -> 4 |
| plasmic pumpkin | `$683D` | `$D0` -> `$F4` | the heart's icon -> its own |
| plasmic pumpkin | `$684A` | `$BE` -> `$9E` | palette 5 -> 4 |

**MARIA palette 5 is `$00 $11 $14` -- its first colour is pure black.** The
crypt key's thirty lit pixels are *all* colour 1, so it renders entirely black
and reads as nothing at all. The necklace is 22 pixels of colour 1 and 13 of
colour 2 (`$11`, nearly black), which is why it is a smudge rather than a
necklace. The weapons in the same tables use palette 4 (`$1A $22 $0D`), whose
first colour is a light gold, and they are perfectly legible -- so the repair
moves those two items across.

The world-sprite table two tables over settles it. `dat_51A5` gives the crypt
key and the necklace palette `$9E` when they are lying on the ground -- the
repair only makes the icon agree with the item.

The pumpkin has a second fault: its graphics entry names `$D0`, the **heart's**
icon. Its own is `$F4`, exactly as `dat_5195` has it. On the ground the pumpkin
uses palette 6 -- the only other item on it is the diamond -- and palette 6 is
randomised every frame (`STA P6C1 / EOR #$F0 -> P6C2 / ADC #$10 -> P6C3`), which
is why those two sparkle where nothing else does. The status strip holds its
palettes fixed for the whole zone and cannot do that, so on palette 5 the
corrected artwork still renders as a dim brown outline. Palette 4 gives it
the orange body and pale stalk it should have.

Four bytes, verified on screen against the stock cartridge: the crypt key
appears in gold where there was nothing at all, the necklace becomes a beaded
gold ring instead of a smudge, and the pumpkin draws its own artwork lit.

## The reticle leg

The last frame of a special actor's death draws four eight-pixel fragments, and
the fourth names **gfx `$EE`** -- the same eight pixels the Grampa screen uses
for its item-select reticle. A targeting bracket appears briefly as the corpse's
right leg:

```
f6:$49EA  E0                 page $E0
          FE EF E8 FB        fragment, gfx $E8
          FE 19 EA FB        fragment, gfx $EA
          BE F2 EC 0E        fragment, gfx $EC   the left leg
          BE 16 EE 0E        fragment, gfx $EE   <- the reticle
          00
```

The artwork has no fourth fragment to reach for: `$EC` and `$EE` are the two
halves of one 16-pixel cell, and the right half *is* the reticle. So **use a
melt fragment** points the fourth fragment at `$EC` as well, giving the corpse
two of the same melt piece rather than a bracket. One byte, and nothing moves --
only which eight pixels are fetched.

## The debug hook, repaired

`DbgPauseHook` (`b0:$BDC2`) runs every frame while the console **PAUSE** switch
is held. It counts presses of the first button and, at four, refills blood
purity and grants +8 maximum health.

**As shipped it can never get there.** Steps 0 and 3 reach the button reader,
but steps 1 and 2 branch to `$BDFA` -- an orphaned three-instruction run that
reads a different button combination and then falls into `$BE00`, which is data.
Both wrong-button exits branch into data as well. Since the IRQ vector is the
reset entry, each is a soft reboot rather than a hang: the counter can be
advanced exactly once before the next invocation restarts the game.

The **repair it** checkbox in the Items tab fixes it with **four branch
operands and nothing else**:

| at | stock | repaired | |
|---|---|---|---|
| `b0:$BDC9` | `$2F` -> `$BDFA` | `$1B` -> `$BDE6` | step 1 joins the reader |
| `b0:$BDCD` | `$2B` -> `$BDFA` | `$17` -> `$BDE6` | step 2 joins the reader |
| `b0:$BDEC` | `$20` -> `$BE0E` | `$0B` -> `$BDF9` | other button -> RTS |
| `b0:$BDF0` | `$21` -> `$BE13` | `$07` -> `$BDF9` | no first button -> RTS |

No instruction moves, no byte outside those four changes, and the orphaned run
at `$BDFA` is left alone rather than reclaimed. Unticking restores the stock
bytes exactly.

Verified by running the routine on an interpreter, stock and repaired:

```
stock      frame 0: dbg_step 1        frame 1: opcode $08 at $BE00 -- into data
repaired   frames 0-3: dbg_step 1,2,3,4
           frame 4: hp_max $27 -> $2F, purity 50 -> 100, counter reset
```

To use it: hold **PAUSE**, then tap the first button four times with the other
buttons released. Each cycle grants another +8, so it repeats.

## Terrain properties

Painting changes how a tile **looks**; this changes what it **does**. They are
separate: the grid holds a character number, and behaviour comes from the area's
property table indexed by `(cell >> 1) & $7F`. Six tables of 128 bytes cover all
76 rooms, so the panel reports how many rooms share the one you are editing.

`CheckTerrainUnderPlayer` (`f6:$55E3`) branches three ways:

| byte | meaning |
|---|---|
| `$00` | open ground |
| bits 0-1 = `3` | solid, blocks everywhere |
| bits 0-1 = `1` or `2` | blocks only that half of the cell diagonal |
| bit 7 set | a scripted square, latched into `pending_terrain` |

**Two adjacent characters always share one entry**, because the index is the
character number shifted right. So properties are coarser than the painter: you
cannot make one tile of a pair solid and its neighbour open.

The panel lists only the entries the current room actually reaches -- 58 of 128
for room `$01` -- and names each one, so a scripted square reads as "door to
`$16`, needs a weapon" rather than `$84`. Each row also **draws the tiles it
governs**, because the property index is the character number shifted right and
that is hard to hold in your head while painting.

Values with bit 2 set are tagged **water**. The engine never tests that bit --
the collision check is only `AND #$03` -- so `$05`/`$06`/`$07` block exactly as
`$01`/`$02`/`$03` do; it is an authoring marker. The necklace crossing is a
hardcoded rectangle in room `$01` and does not consult the terrain at all, so
the same water elsewhere stays impassable.

## Doors

A door *is* a terrain property with bit 7 set; which squares are doors is set in
the property table above. What the **Exits** tab adds is where each one goes and
what it demands:

| code | route | condition |
|---|---|---|
| `$81` | `$11` -> `$2B` | none |
| `$82` | `$01` -> `$14` | needs a weapon |
| `$83` | `$08` -> `$15` | forces a message |
| `$84` | `$13` -> `$16` | needs `weapon_level > 0` |
| `$85` | `$17` -> `$1E` | needs the crypt key **selected** |
| `$86` | `$40` -> `$1C` | needs the Ram beaten, a weapon, nothing selected |
| `$90` | `$16` <-> `$36` | paired, both directions editable |

Destinations are validated against the 76 real rooms, so a door cannot be
pointed at a kind that has no header. The two `boss_flags` gate masks are
editable beside them.

## Text

All **114 records**, searchable and edited in place. Two framings, both handled:

* **A** -- `$FF <p1> <p2> '@' text '#'`, the dialogue pool
* **B** -- `<$FE|$FF> <p1> <p2> text`, running to the next `$FE`/`$FF`, used by
  the credits and cutscenes

Records are packed end to end, so replacement text may be **shorter but never
longer**; a short one is padded with spaces rather than moving everything after
it. The box enforces the limit as you type and the write is refused outright if
it would overrun. Control codes are `|` newline, `&` new page, `^` apostrophe,
`*` glyph.

One record the editor finds that `TEXT.md` does not: `f6:$6A6C`, the status-bar
template -- `BLOOD / PURE SCORE HEALTH:`. `text.py` runs its two framing scans
independently and this one falls between them.

## Bosses

Each fight is a 32-byte setup record reached through a pointer table; slot 0 is
null and the three bosses are numbered 1-3.

| | Skull | Ram | Dr Evil |
|---|---|---|---|
| record | `b5:$B1A7` | `b5:$B1C7` | `b5:$B1E7` |
| health | 64 | 40 | 160 |
| contact | 10 | 5 | 9 |

**Health is a hit count, not a pool.** Every weapon takes exactly one point per
hit, so the axe and the mega blaster differ only in how often they land, and the
knife is refused outright. Halving a boss's health halves the fight for every
weapon equally.

Contact damage is not in the record but in a table indexed by `mode_flag`, whose
base at `$BBFD` overlaps an `RTS`. Entry 0 is that `$60` byte and is never read,
because `mode_flag` is 1-3 throughout a fight.

Also editable per boss: the palette set, the fire direction, the player's start
position, and the stage counter's starting value -- the escalation index, `$00`
for all three as shipped, so every fight begins at its calmest.

### What winning is worth

`BossSequenceReward` (`b5:$B637`) applies both:

| | at | stock |
|---|---|---|
| victory raises `hp_max` by | `b5:$B63A` | `$10` |
| victory sets blood purity to | `b5:$B640` | `$64` |

The `hp_max` gain matters beyond the number: it is **the only source besides the
diamond, and twice as generous**. Beating all three bosses is worth `$30` on its
own -- more than the two diamonds a second life normally costs -- so boss
progress quietly buys revival as well. The purity refill undoes every drain
taken on the way in.

## Drawing: characters and sprites

Both work like the room editor with the scale changed: pick a value, click a
cell. In the **Draw** tab a cell is one pixel.

The tab edits two kinds of artwork through one path, because they are the same
format. MARIA forms the address as `(page << 8) | low` and scanline *n* of a
zone reads page + *n*, so a terrain character (2 bytes x 16 lines in an area
bank) and a sprite cell (4 bytes x 16 lines on bank 7) differ only in width and
where they live.

| source | what is in it |
|---|---|
| room characters | the area bank's set, 8 x 16, coloured by band |
| sprites `$C0` | the player and the zombies |
| sprites `$E0` | ghosts, wolves, spiders, bats, crows, item icons, Grampa, the UI and the message font |

Cells are named from `build/_spritenames.py` -- 125 of them -- and each name
carries how it was identified: from the code, from play, or as a guess.

Two things about sprites specifically:

* **They store no colour.** A character takes its three colours from the band it
  is drawn in; a sprite takes them from the composite record at draw time. The
  tab previews sprites on a neutral ramp for that reason.
* **A 16-pixel cell often holds two 8-pixel sprites.** `$E0/$D0` is the heart
  *and* the necklace, `$D4` the cross *and* the crypt key. You are editing the
  pair.

Sprite pages are global -- there is no per-room copy, so every appearance
changes at once.

A pixel is **two bits**, so it has exactly four values and only three of them
are colours -- value 0 is transparent, and the tab draws it as a checker rather
than as black so you can tell a hole from a dark pixel. Which three colours the
other values mean depends on the band the character is drawn in, so the tab has
a band selector; the character itself stores no colour at all.

The **Colour** tab edits every palette block in the cartridge against the whole
7800 space -- sixteen hues across, sixteen luminances down, hue 0 the grey
column. Luminance and hue are independent, which is why the picker is a grid
and not a list.

| block | where | shape | colours |
|---|---|---|---|
| the room's own | via the area's stream | 10 bands x 3 | the terrain |
| Grampa | `b0:$A581` | 8 palettes x 3 | **everything drawn over the terrain** |
| intro | `b3:$81C9` | 8 palettes x 3 | the intro, then replaced |
| boss sets 1-3 | `b5:$B20F`, `$B237`, `$B25F` | 10 bands x 3 | each boss fight |

The Grampa block is the one that matters in normal play: it is reloaded every
time the inventory opens, so it is what colours the player, the creatures and
the item icons. Each of its eight palettes is listed with the items that draw
from it, taken from `tbl_ItemIconPal` -- palette 4, for instance, is the crypt
key, necklace, heart, knife, axe, blaster and mega blaster at once.

Both are shared, and both say so before you commit:

* a character set is drawn by every room in its bank with the same CHARBASE --
  `b1` charbase `$80` covers 19 rooms
* a palette block is shared by every room with the same stream -- stream `$12`
  covers 11

Editing a character updates the room picture immediately, since the room is
drawn from that same character set.

## Dark rooms

The editor draws lit, because you cannot paint what you cannot see. A room
flagged dark gets an **as played (dark)** toggle in the toolbar showing what a
player actually gets: `f7:$F134` collapses every colour to `$00` or `$02`, which
in most bands is pure black. Holding the lantern clears `area_is_dark` outright,
so the normal lit view is also the with-lantern view.

Worth knowing before flagging a room dark: the lantern is item `$09`, and it
sits in room `$1B`. Any room a player reaches before that one is genuinely
unlit for them.

## What it needs

**Not the disassembly.** The editor reads the cartridge itself -- every table,
header and pointer is resolved from the ROM at load -- so `src/`,
`annotations.json` and the rebuild are no part of it. Verified by running it
from a copy holding nothing but `tools/` and a `.a78`: all 76 rooms, 114 text
records, 12 songs, 29 item references, the terrain properties, the palette
blocks, the song preview, editing, saving and patch export all worked.

Two optional files add **names**, not function:

| | supplies | without it |
|---|---|---|
| `build/regions.json` | which region each room belongs to | every room reads "Unassigned" |
| `build/_spritenames.py` | the 125 sprite cell identifications | cells show offsets only |

Both are read inside a `try`, so a missing one costs a label and nothing else.
The only directory the editor writes to on its own is `build/`, for the
song-preview WAV it renders and deletes.

## Both releases

The editor identifies the cartridge on load, prints it, and shows it as a badge
beside the filename in the title bar -- orange for **NTSC**, blue for **PAL** --
so which layout is in play is visible at a glance rather than only in the
console:

```
  cartridge : Midnight Mutants (Europe).a78
  version   : PAL
```

Addresses here are the NTSC ones; the European release moves bank 6 by +3 and
part of bank 7 by +9 for its taller display list, so `romedit.py` relocates its
address tables once at load and every accessor works unchanged on both. The
addresses shown in the UI are the loaded image's own, so they match that
version's listings. An image matching neither layout is refused rather than
edited blind. See `VERSIONS.md`.

Colours are converted with the NTSC decoder either way, so a European
cartridge's swatches are approximate -- the palette bytes are exact.

## The panels

Ten tabs down the right-hand side: Tiles, Room, Exits, Actors, Items, Bosses,
Text, Draw, Colour and Changes. They wrap onto two rows rather than being
squeezed onto one -- each tab is sized to its own label and can grow to share a
row but never shrink below it, so nothing is ever clipped off the edge. Each
panel scrolls independently of the room picture.

## Patches leave the header out

A patch is built against the **cartridge data alone**, with the 128-byte `.a78`
header excluded. The header is not part of the ROM -- it tells an emulator how
to map the file -- and the same dump ships behind different ones. Our Europe
image and Trebor's PAL hold byte-identical data but declare different cart
types (`$0002` against `$0012`, the latter carrying the `bank6@$4000` bit our
engine needs), so a header-inclusive patch made on one was refused by the other
over a difference that changes nothing about the game.

Patching the body fixes that: **one patch fits either header**, and the header
of whatever image it is applied to is kept. A 46-byte patch made on the Europe
file now applies cleanly to Trebor's PAL and leaves its corrected cart type
alone.

Region safety is unaffected, because it never depended on the header: NTSC and
PAL bodies differ in 16,467 bytes, so their CRC32s differ and a patch for one is
still refused by the other.

Patches written before this still load. They are recognised by declaring a
source 128 bytes longer than the ROM, applied the old way, and flagged with a
note suggesting a re-export.

## Patch files

The **Changes** tab writes and reads patches: only the bytes that differ, plus
the checks to make sure they land on the right cartridge. Eight changed bytes
come out as an **82-byte patch** against a 131,200-byte ROM.

The format is **BPS**, not something invented here, so a patch written by the
editor applies with Floating IPS, RomPatcher.js or beat, and theirs applies
here. `tools/bps.py` implements it and can be used on its own:

```
python tools/bps.py create <original.a78> <modified.a78> <out.bps>
python tools/bps.py apply  <original.a78> <patch.bps> <out.a78>
python tools/bps.py info   <patch.bps>
```

### Why BPS rather than IPS

| | verifies |
|---|---|
| IPS | **nothing** -- offsets and data only, and a 24-bit offset ceiling |
| UPS | CRC32 of source, target and patch; less well supported today |
| **BPS** | CRC32 of source, target and the patch itself; what current tools default to |

IPS is the most widely supported format and the wrong choice here: applied to
the wrong ROM it corrupts it silently, which is exactly the failure the checks
are meant to catch.

### What is checked, and when

A BPS patch ends with three CRC32s -- the ROM it was made from, the ROM it
produces, and the patch body. All three are verified:

* **on load**, the patch's own checksum, so a truncated or corrupted file is
  refused before it touches anything;
* **before applying**, the source checksum against your cartridge. A mismatch
  is reported with both values and needs explicit confirmation;
* **after applying**, the result against what the patch expects.

Loading a patch applies it over the cartridge **as it is on disk**, replacing
unsaved edits, so a patch is always relative to the stock image rather than to
whatever happened to be in memory. Exporting is refused if any of the 76 rooms
no longer parses, the same guard Save uses.

## Safety

* **Save is refused** if any of the 76 rooms no longer parses, so a header edit
  that corrupts the structure cannot reach a file.
* **Revert** restores the in-memory image to the file on disk.
* The **Changes** tab lists every differing byte as `rom+offset  from -> to`.
* The original file is never written; Save always asks for a destination and
  defaults to `<name> (edited).a78`.

## How it renders

The server sends the browser the same three things the game uses to draw a
room -- the 1000-byte grid that `f7:$F243` assembles, the area bank's character
set, and the palette block -- and the browser draws from those bytes. The
editor's picture is therefore the cartridge's own, not a second implementation
that could drift from `rooms.py`.

Two details that are easy to get wrong and are handled here: characters are
**two bytes wide** (CTRL `$50` sets CWIDTH), so only even character numbers are
real tiles and the picker shows 128 of them; and a zone's line offset **counts
down**, so line 0 of a character reads the highest page.

## Layout

```
tools/romedit.py     the write side: a mutable Cart plus structured accessors
tools/editor.py      HTTP server and JSON API over it
tools/editor_ui/     index.html, app.js, style.css
```

`romedit.py` is usable on its own for scripted edits:

```python
from romedit import RomEdit
r = RomEdit("midnight.a78")
r.set_item(0x43, iid=0x0D)          # put the axe where the knife was
r.paint(0x01, col=5, band=9, cell=0x2A)
r.save("out.a78")
```

Running it directly audits the cartridge and reports slice sharing:

```
python tools/romedit.py <rom.a78>
```
