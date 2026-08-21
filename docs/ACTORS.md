# Midnight Mutants -- actor reference

Everything here is read from the ROM or measured in play. The **appearance**
column is the weakest: graphic indices are known, but which drawn creature
each corresponds to has only been matched where play reports pinned it.

## The three populations

| population | lives in | health | dies at | contact damage |
|---|---|---|---|---|
| ordinary actors | 8 slots, `$8F`-`$B7` | `actor_mode` itself | reaches `$A0` | scaled or blood-only |
| special actors | 4 slots, `$DD`/`$E1` | `sactor_damage` `$1E81` | 8-bit overflow | **`$10` fixed** |
| bosses | bank 5, own state | `boss_health` `$1EA3` | counts down to 0 | own logic |

## Ordinary actors -- spawn mode is the health

Toughness is `$A0` minus the spawn value; each hit adds `weapon_level`.

| spawn | hits: axe / blaster / mega | knife | contact | seen as |
|---|---|---|---|---|
| `$FF` | 1 / 1 / 1 | kills | blood only | crows, bats |
| `$FE` | 1 / 1 / 1 | kills | blood only | crows, bats, wolves |
| `$FD` | 1 / 1 / 1 | kills | n/a | **enemy projectiles** |
| `$98` | 8 / 4 / 3 | never | scaled | tough ground enemy |

Contact damage for a tough actor (`$80`-`$9F`) is `boss_flags * 2 + 2`:

| bosses beaten | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| health per touch | 2 | 4 | 6 | 8 |

Halved by the cross. Spiders measure exactly on this curve, so they are
ordinary tough actors -- and per the table above, the knife never kills one.

## Special actors -- seeded from kind

`sactor_kind` (`$1E91`) selects a seed from `tbl_SactorToughness` (`f6:$6433`);
death is overflow past `$FF`, so cost is `256 - seed`.

| kind | seed | points | axe | blaster | mega |
|---|---|---|---|---|---|
| 0 | `$FC` | 4 | 4 | 2 | 2 |
| 1 | `$FE` | 2 | 2 | 1 | 1 |
| 2 | `$F9` | 7 | 7 | 4 | 3 |
| 3 | `$F4` | 12 | 12 | 6 | 4 |
| 4 | `$F8` | 8 | 8 | 4 | 3 |
| 5 | `$F7` | 9 | 9 | 5 | 3 |
| 6 | `$F1` | 15 | 15 | 8 | 5 |
| 7 | `$F7` | 9 | 9 | 5 | 3 |
| 8 | `$C4` | 60 | 60 | 30 | 20 |
| 9 | `$C4` | 60 | 60 | 30 | 20 |
| 12 | `$EC` | 20 | 20 | 10 | 7 |

The table is **13 bytes**, `$6433`-`$643F`, and `dat_6440` -- the head graphics
-- begins immediately after it. Kinds above 12 therefore have no entry: an index
past the end reads artwork. `PickSactorKind` cannot produce one in any case,
since its fixed entries stop at `$0C` and its random specs are masked `AND #$07`.

All immune to the knife. Contact costs a flat **16 health** (`f6:$6717`),
regardless of boss progress -- four times the worst an ordinary enemy does.

Ghosts are neither -- see their own section below.

## What spawns where

`tbl_ScreenKind` (`f6:$6753`) is indexed by `screen_kind_idx` (`$8A`), one
entry per screen. A positive entry pins a single kind; a negative entry is a
random draw whose low three bits are the mask. Crossing that with
`tbl_SactorToughness` gives the enemy strength a screen can actually produce:

| entry | screens | kinds | points to kill | mega-blaster hits |
|---|---|---|---|---|
| `$F3` | 20 | random 0-3 | 2-12 | 1-4 |
| `$FF` | 20 | random 0-7 | 2-15 | 1-5 |
| `$0C` | 16 | always 12 | 20-20 | 7-7 |
| `$01` | 8 | always 1 | 2-2 | 1-1 |
| `$09` | 6 | always 9 | 60-60 | 20-20 |
| `$06` | 4 | always 6 | 15-15 | 5-5 |
| `$F7` | 2 | random 0-7 | 2-15 | 1-5 |
| `$0A` | 2 | always 10 | - | - |
| `$07` | 1 | always 7 | 9-9 | 3-3 |
| `$08` | 1 | always 8 | 60-60 | 20-20 |

So a screen with `$F3` can throw anything from a 2-point nuisance up to a
12-point enemy, while `$0C` pins every spawn to kind 12 at 20 points. The
`$FF` and `$F7` entries draw across the whole 0-7 range, which is the widest
variety in the game -- and notably none of those low kinds is one of the
60-to-80 point monsters, which are placed rather than randomly drawn.


## Both death countdowns index one past their table

`sub_5BCC` draws a dying ordinary actor with `LDA actor_mode,X : TAY : LDA
dat_5CE6,Y` -- the mode used directly as the index -- and the kill at `f6:$5DAD`
seeds it `$08`. `dat_5CE6` is eight entries, `$5CE6`-`$5CED`, and `sub_5CEE`
starts at `$5CEE`, so the first frame reads that routine's `$A5` opcode as a
sprite number. Every crow, bat and ground enemy plays it.

The ghost has the same defect with an extra halving: state `$10`, index 8,
table `dat_6219` of eight entries followed by `sub_6221`.

Seeding `$07` and `$0F` keeps both inside their tables. Nothing else tests
either value.

## Ghosts -- their own pair, and killable after all

Ghosts are neither ordinary nor special actors. They occupy a dedicated pair with
positions at `$1EAD`/`$1EAF` and health at `$1EB3`/`$1EB4`.

| property | value |
|---|---|
| seeded at | `$E0` (`f6:$6204`) |
| cost to kill | 32 points |
| per hit | `weapon_level + 1` -- the `SEC` before `ADC` adds the carry |
| knife | **1 per hit, 32 hits** -- the only enemy the knife can kill |
| axe / blaster / mega | 2 / 3 / 4 per hit -> 16 / 11 / 8 hits |
| on death | 20 points, state `$10` |
| contact | `hp_max` **-8**, floored at `$11`, 40-frame cooldown |

The collision is at `f6:$6240`, a separate handler from both the actor and
special-actor loops. Ghosts can be hit; they simply take a lot of shots, and
their death is a wave and a grin rather than the usual animation.

Ghosts are also the only enemy that attacks the health *ceiling* rather than
current health, which is why a long crypt fight quietly undoes diamonds.

### The first frame of their death is out of bounds

The death animation indexes `dat_6219` with the state halved, and the kill at
`f6:$6268` seeds the state `$10`. `$10 >> 1` is 8, but the table is eight entries
(`$6219`-`$6220`) and `sub_6221` starts at `$6221`. The first frame reads that
routine's `$A5` opcode as a sprite number.

Because a ghost is drawn as a top half plus `top + $20`, the frame renders `$A5`
over `$C5` -- a misaligned slice of the mega blaster's orb above a misaligned
slice of the AWESOME lettering. It shows in play as a single frame of stray text
when a ghost dies. Seeding `$0F` instead keeps the index at 7 or below.

## Appearance

Graphic indices are known; the mapping to drawn creatures is not.

| context | frames |
|---|---|
| straight-line movers (`$FD`) | `$80`, `$82`, `$84`, `$86` |
| chasing behaviour (`$FF`) | `$10`, `$10`, `$14`, `$14` |
| death animation | `$00`, `$00`, `$04`, `$04`, `$08`, `$08`, `$0C`, `$0C` ... |

Each is a character number into the area's set; the sheets are in
`build/gfx/`. Matching index to creature needs a capture that records
`disp_gfx` alongside a screenshot -- not yet done.

## The cross suppresses spawning

Measured, then traced to the instruction.

| room | stock | with cross |
|---|---|---|
| `$04` | 8 live | 0 |
| `$05` | 8 live | 0 |
| `$06` | 8 live | 0 |
| `$11` (cliffs) | 4 live | 2 |

Counts are occupied slots of the 8-slot ordinary actor array (`actor_mode`,
`$AF`), peak over each room visit, walking one recorded route on the stock cart
and on a build whose only change is the cross in inventory (`--item 01=1`).

### The mechanism

`LoadAreaHeader` (`f7:$F00C`) reads each area's special-actor definition bytes
from its record stream. One of them is checked against a marker:

```
    LDA (src_ptr_lo),Y      ; the area's def byte
    CMP #$EF
    BNE L_F06D              ; not the marker -- use as authored
    LDA #$22                ; marker $EF: default
    LDX itm_cross           ; $1F3E
    BNE L_F06D              ;   holding the cross -> keep $22
    LDA #$FF                ;   not holding it    -> $FF
  L_F06D:
    JSR ExpandAreaDef
    STA sactor_def1
```

`ExpandAreaDef` (`f7:$F280`) splits the byte into two nibbles: the high nibble
indexes `tbl_DefAmount` (`$F296`) for how many, the low nibble indexes
`tbl_DefRateMask` (`$F2A5`) for how often. A rate mask of `$00` passes every
time; `$3F` passes one time in 64.

| def byte | amount | rate mask | effect |
|---|---|---|---|
| `$FF` (no cross) | `$FF` | `$00` | unbounded, spawning constantly |
| `$22` (cross) | `$02` | `$3F` | two, one chance in 64 |

Both lookups for `$FF` land one byte past their 15-entry tables -- amount index
15 reads `$FF` and rate index 15 reads `$00`, verified against the raw ROM
image, whatever the authors intended.

Confirmed on the machine: in rooms `$01`, `$04`, `$05`, `$06` and `$11` the
expanded pair is `def1=$FF rate=$00` on the stock cart and `def1=$02 rate=$3F`
with the cross held -- exactly what the tables predict.

So the effect is authored per area, not global: only areas carrying the `$EF`
marker respond to the cross at all. It also explains the potion room `$0B`
independently -- that area's amount is authored `$00`, so it is empty either
way.

`boss_flags = $01` was ruled out as a cause: the same recording on a
boss-flags-only build follows an identical 12-room route with counts identical
to stock.

### Special-actor liveness

A slot is live when **`sactor_damage` (`$1E81`) has bit 7 set**. That is the
game's own test: the collision loop at `f6:$66FE` does

    LDA sactor_damage,X
    BPL skip                 ; bit 7 clear -> slot not active

and `f6:$529E` ORs the same four bytes to decide when an area releases its item,
so `$00` means empty.

`sactor_pos_long` (`$DD`) is **not** liveness -- position persists in a slot
after it goes inactive, so it reads nonzero in rooms that are empty in play.

Measured with the correct test, walking one route on the stock cart and on a
cross-only build:

| room | ordinary | special | in play |
|---|---|---|---|
| `$04` | 0 | **1** | one zombie |
| `$05` | 0 | 0 | empty |
| `$06` | 0 | 0 | empty |
| `$11` | 2 | 0 | cliffs, bats |

So the survivor in a cross-held room is a special actor, and everything the
cross suppresses is an ordinary one.

Reproduce with `tools/mame/bats.lua` or the two-array variant.

## The cross: the complete list

Found by scanning all eight banks for every opcode that can reference `$1F3E`,
plus the one `sel_item == $01` test. Seven machine-code references and one
selected-item check, and that is all of them.

| where | effect |
|---|---|
| `f6:$5FA7` | **selected**: immune to contact blood loss |
| `f6:$5FB0` | owned: contact blood loss halved |
| `f7:$D403` | owned: every source of health damage halved (`DamageHealth`) |
| `f7:$F066` | area def byte `$EF` becomes `$22` instead of `$FF` -- amount 2 at 1-in-64 instead of unbounded and constant |
| `f7:$F1FC` | clamps `ram_1E76` to 3 and sets bit 7 of `ram_1E6D`, a further per-area spawn limit |
| `f6:$5D01` | three times in four an actor picks a random destination instead of homing on the player |
| `f6:$4EB2` | when blood purity reaches zero, `undead_flag` is `$FF` holding the cross and `$FE` without. Same message, same finality -- but without the cross the player's sprite becomes the **bat**, drawn from page `$E0` with the bat's own cells `$10`/`$14`. With it you stay a standing figure on the player's page. See `PLAYER.md` |
| `b0:$A40B` | Grampa's message index: `$17` without, `$18`/`$19` at random with |

Scanning for opcode and operand across all eight banks bounds the answer in a
way that following code paths cannot: it establishes that these eight are the
complete set, not merely the ones reached so far.

## Appearance, kind and room are one chain

The sprite work and the behaviour work meet here.

### Head sprite from kind and facing

`sub_63F5` (`f6:$63F5`) builds the index and reads the head cell:

    LDA sactor_facing,X
    ASL A : ASL A          ; facing * 4
    ADC sactor_kind,X      ; + kind
    TAX
    LDA dat_6440,X         ; f6:$6440 -- the head sprite's low byte
    STA disp_gfx,Y
    LDA dat_6480,X         ; its companion

`dat_6440` holds values like `$A2`, `$AA`, `$B6`, `$BA` -- **odd offsets, two
past a cell boundary**. That is the code confirming that page `$C0` packs two
8-pixel sprites per 16-pixel cell: the game addresses the right-hand half
directly. The split was found by eye first and is corroborated here.

### Kind from the room

`PickSactorKind` (`f6:$6741`):

    LDY screen_kind_idx
    LDA tbl_ScreenKind,Y      ; f6:$6753, one byte per room
    BPL done                  ; bit 7 clear -> the value IS the kind
    AND #$07                  ; bit 7 set -> mask
    JSR Random : AND mask     ; -> a random kind in 0..mask

So a room either pins one kind or draws at random from a small range, and
`tbl_ScreenKind` is what "only spawns in the caves" actually means.

### The casts, and they match play

| rooms | cast |
|---|---|
| `$20`-`$2F`, `$40` -- the caverns | bignose, **humpback**, lab-pair zombie |
| `$18`-`$1B`, `$46`, `$4F` -- the pumpkin fields | longneck, **pumpkin-head**, zombie |
| `$1C`, `$33`-`$3C`, `$41`-`$47` | **Dr Evil zombie**, bignose, bulb-head |
| `$0E` -- a dark field | headless, hunchback |
| most of the opening area | Dr Evil zombie, bignose, bulb-head, headless |

The humpbacks land in the caverns and the pumpkin-heads in the pumpkin patch,
neither of which was fed in -- the names came from the artwork, the rooms from
`tbl_ScreenKind`, and they agree.

Toughness comes from the same kind index through `tbl_SactorToughness`
(`f6:$6433`), so a room's byte fixes appearance, colour (`dat_67C9`/`dat_67E9`)
and durability together. `build/cast.json` has the full per-room list.


## Three damage rules

Every weapon is a projectile, so all of this happens in projectile collision.
What a hit removes depends on the target:

| target | damage per hit |
|---|---|
| most actors, ordinary and special | `weapon_level` -- the knife is level 0, so it never kills them |
| ghosts | `weapon_level + 1` |
| bosses | 1 flat, unless the weapon is the knife |

The ghost rule is visible: the collision loop at `f6:$623B` ends with

    LDA ghost0_active,X
    SEC
    ADC weapon_level        ; the SEC is the +1
    BCC still_alive

The ordinary rule checks out arithmetically. A spawn seeded `$98` needs 8 steps
to reach death at `$A0`, and the measured hit counts are 8 with the axe, 4 with
the blaster and 3 with the mega blaster -- exactly `weapon_level` per hit at
levels 1, 2 and 3, with the knife at 0 never finishing the job.

`tbl_SactorToughness` seeds count up to `$00` instead, so a special actor's
durability in steps is `$100 - seed`: 12 for the hunchback, 7 for the longneck,
plain and pumpkin-head zombies, 4 for the humpback, bignose and lab-pair, and 2
for the bulb-head and Dr Evil zombies.

The collision site is `f6:$5D86`, and it does not touch `sactor_damage` at all:

    LDA actor_mode,X
    CMP #$A0 : BCS died      ; already over the threshold
    ADC weapon_level         ; the damage is the weapon level
    STA actor_mode,X
    CMP #$A0 : BCS died      ; crossed it now
      $13 -> survived, and flash for $1E frames
    died:
      $12 -> killed

`actor_mode` doubles as the accumulator: it *is* the damage counter, and the
actor dies when it passes `$A0`. The two sound effects are the two branches, so
the game tells you by ear whether a shot was fatal. The rule above was derived
from hit counts before the line was found; the line agrees with it.

## A special actor is two display slots

`sub_5155` allocates by scanning for a slot where **both** `disp_active,Y` and
`ram_1DF9,Y` are clear -- and `$1DF9` is `disp_active + 1`. So a sactor needs two
consecutive slots and uses both: Y for the head, Y+1 for the body.

### The body, while alive

`f6:$638F`, every frame:

    INC ram_1E85,X          ; per-actor walk counter
    LDA ram_1E85,X
    AND #$03                ; four frames
    ADC sactor_facing,X     ; + facing, already stored x4 (0/4/8/12)
    ORA ram_00F5            ; | base from dat_67C9[kind]
    LDY ram_1E95,X
    STA ram_1E29,Y          ; slot Y+1's graphics low byte

`ram_00F5` is `$50` for kinds 0-11 and `$70` for kind 12, so the body cycle is
`$50`-`$5F` for most of the cast and `$70`-`$7F` for the humpback: four frames
per facing, sixteen in all. That is a different base from the heads, and it is
why the humpback both looks different and is 4 bytes wide instead of 2.

### The death animation

Two things happen at once, and both are visible in the code.

The head is **thrown**. `sub_63BF` positions it at

    sactor_pos_cross + $10 - 2 * sactor_damage

so as the damage counter runs up toward `$00` the head rises, and its facing is
taken from `dat_63E1` = `$00 $08 $04 $0C` indexed by `sactor_damage & 3`, so it
tumbles through all four directions on the way.

The body **breaks up**. `f6:$62DD` replaces the live walk frame with

    LDA sactor_damage,X : LSR A : TAY
    LDA dat_6641,Y      ; $65 $65 $64 $63 $62 $61 $60

a seven-step sequence counting downward from `$65` to `$60` as the counter
falls. That is the split-and-melt sequence seen in play.

### Resolved: the body's page comes from the composite record

The body's low byte indexes `dat_455C`, a table of pointers to composite
records, and the first byte of each record IS the page. So no separate high byte
is needed. The pointer table spans banks: most records sit near `$48F0` in bank
6, but the humpback's are at `$D045` and up in bank 7.


## Colour

A part's MARIA palette is the top three bits of its palette-and-width byte:
typically 7 for head and torso, 5 for legs, and 2, 4 or 6 for a few types.

* palettes 0-6 come from a 33-byte block at `b3:$81C9`, copied into `$20`-`$40`
* palette 7 is rewritten per kind by `sub_67A3` from `dat_67E9`
* `DLI_Handler_A` reloads palettes 0 and 1 per display zone from
  `zone_pal_shadow` (`$1ECC`), with `dat_40A8` choosing the register set --
  so those two vary with a sprite's vertical position on screen

**Resolved.** Palette 6 has no fixed value at all: `f6:$4C70` rewrites all three
of its registers every frame from the random generator --

    JSR Random
    STA P6C1        ; a random colour byte
    EOR #$F0        ; hue nibble flipped, luma kept
    STA P6C2
    ADC #$10        ; one hue step further
    STA P6C3

-- so the entries are always `c`, `c^$F0` and `(c^$F0)+$10`: hue-contrasted at
matched luminance, which is why it strobes rather than flickering as noise.
`sub_4329` forces any part into palette 6 while its flash flag is set, and the
bulb-head is authored to use it permanently.

Palettes 2-5 are now sourced. Exactly two block copies write them in the whole
ROM -- `b3:$81C9` during the intro and `b0:$A581` when the Grampa screen opens --
and nothing reloads them on area entry, so the world keeps whichever ran last.
Since the inventory is opened constantly, the Grampa block is the live one for
almost all of play. See `SPRITES.md`.

Colour bytes convert through `tools/palette.py`, which sets luminance from the
luma nibble and adds the hue's offset from its own grey level at constant
amplitude. `gfx.py` derives hue from a phase formula instead, which places hue 9
in the olive range rather than blue, so its output is not colour-accurate.


## Two animations that are not in the sprite data

### The head bob belongs to kind 0 alone

`sub_63E5` pushes `sactor_kind` before drawing and pops it at `f6:$6417`:

    PLA
    BNE L_6432            ; any kind but 0 -- no bob
    LDA frame_ctr
    ASL A : ASL A : ASL A : ASL A
    TAX
    LDA dat_DD00,X
    LSR A x5
    CLC : ADC disp_pos_cross,Y : SBC #$02
    STA disp_pos_cross,Y

so the head gets a per-frame vertical offset only when the kind is zero. Three
kinds draw the bignose zombie -- 0, 1 and 4 -- and only the first of them bobs.
Confirmed from play before it was found in code.

### Palette 6 is the damage flash

`sub_4329`, drawing each part of a composite:

    LDX ram_0069          ; the flash flag, fed from sactor_flash ($1E99)
    BEQ normal
    AND #$1F              ; keep the width
    ORA #$C0              ; force the palette bits to 6
    STA txt_pal

So palette 6 is not a colour scheme any creature owns; it is what everything
turns while being hit. The bulb-head zombie's authored palette is `$DE` --
palette 6 -- so it draws in the flash palette permanently, which is why it reads
as animated in play and why its colours never resolved from a static table.

That also explains why palettes 4 and 6 look wrong when read straight from the
base block: 6 is a state, not an identity.


## A visible artwork collision

The last frame of the special-actor death animation draws the item-select
reticle as the corpse's right leg. This is in the data, not a misreading:

    $65 -> record at $49EA
    E0                page $E0
    FE F1 E8 FB       2 bytes, gfx $E8, offset -15,-5
    FE 19 EA FB       2 bytes, gfx $EA, offset +25,-5
    BE F2 EC 0E       2 bytes, gfx $EC, offset -14,+14
    BE 16 EE 0E       2 bytes, gfx $EE, offset +22,+14   <-- the reticle
    00

`$EE`-`$EF` is the same eight pixels the Grampa screen uses for the item-select
reticle. Confirmed on screen in play: it appears in the final frame of a
zombie's death, though the flashing palette makes it easy to miss.

Shared artwork is normal in this ROM -- the zombies borrow the player's legs,
the sine table that bobs kind 0's head is the same one that drifts the bats, and
the humpback's body records sit in a different bank from the rest. What makes
this case worth recording is that the reuse is *visible*: a UI element appears
briefly as part of a creature's corpse.

## Which rooms have throwing enemies

`TryThrowProjectile` (`f6:$6085`) is gated by `throw_enable` (`$1FCC`), loaded
per area from header byte `+0F` at `f7:$F0B6`. It is used as an `AND` mask
against the rate counter, so the value is the reciprocal of the throw rate and
every populated entry is a `2^n - 1` mask.

Only **10 rooms of 76** enable it:

| room | mask | throws about 1 frame in | where |
|---|---|---|---|
| `$3C` | `$01` | **2** | Dr. Evil's room |
| `$3B` | `$07` | 8 | approach |
| `$3A` | `$0F` | 16 | approach |
| `$39` | `$1F` | 32 | approach |
| `$1B` | `$0F` | 16 | pumpkin fields |
| `$19`, `$1A` | `$1F` | 32 | pumpkin fields |
| `$18` | `$3F` | 64 | pumpkin fields |
| `$45`, `$46` | `$7F` | 128 | caves |

**The approach to Dr. Evil is a deliberate ramp**: `$39` throws once in 32
frames, `$3A` once in 16, `$3B` once in 8, and his own room `$3C` once in 2.
The density quadruples over the last four rooms.

A thrown projectile takes `actor_mode = $FD`. Because that is above `$A0`, the
ordinary damage model destroys it in one hit, which is why player and enemy
shots annihilate without a special case. Hitting the player runs `sub_5FF6`:
6 health, and 5 purity -- or **9 with the necklace held**.

Confirmed in play: the pumpkin heads in the fields are the throwers there, and a
hit while carrying the necklace does cost 9.

### The cave pair is a corridor

`$45` and `$46` are not scattered. They are consecutive links in a straight
chain -- `$44 -> $45 -> $46 -> $47`, every room on page 8 -- so both must be
crossed and neither can be routed around.

That matters because the necklace is picked up inside the caves. From the moment
you have it, every thrown hit on the way out costs 9 purity instead of 5, and
the exit path runs through two consecutive throwing rooms. The item that opens
the route also makes leaving it more expensive, which is why the caves are
harder to escape than to enter.

Their mask is `$7F`, the slowest in the game -- about one throw in 128 frames
each -- so this is attrition rather than a wall.

## Which creature each screen spawns

`tbl_ScreenKind` gives the kind; the names below are the bestiary's, established
against play rather than guessed from sprite order. Two of them are placed
pairs rather than random spawns, and their `def4` budget says so.

| kind | creature | rooms |
|---|---|---|
| 1 | Bignose | `$1C $33 $35 $41`-`$44 $47` |
| 6 | Pumpkin-head | `$18`-`$1B`, the pumpkin fields |
| 7 | Headless | `$0E` |
| **8** | **Lab-pair zombie** | `$40` only, budget **2** -- the tough pair below the lab |
| **9** | **Dr Evil zombie** | `$38`-`$3C` and `$45`, budget 4 |
| 10 | (no bestiary entry) | `$46 $4F` |
| 12 | Humpback | `$20`-`$2F`, the whole cave run |
| `$F3` | random 0-3 | 20 rooms |
| `$F7`, `$FF` | random 0-7 | 22 rooms |

Kinds 8 and 9 share seed `$C4`, the toughest in the game, and each is pinned to
its own area rather than drawn at random -- the game places its hard encounters
and rolls dice for the rest.

A caution for anyone naming these from the artwork: the sprite order does not
match the kind order. Kind 2 is the Longneck and kind 3 the Hunchback, while
kind 7 is the Headless -- reading them off the sprite sheet in sequence gets
five of the eleven wrong.

## The roaming cast, and which slot spawns it

An area header carries six placement budgets, each a byte split by
`ExpandAreaDef` into an amount (high nibble) and a spawn-rate mask (low nibble).
`def4` is the special actors; the rest are the roaming cast:

| slot | header | spawns | identified by |
|---|---|---|---|
| `def0` | +9 | **crow** | `dat_5E6A` |
| `def1` | +8 | **bat** | `dat_5CE2` |
| `def2` | +10 | **wolf** -- its own slot, see below | `$1FC6`-`$1FCA` |
| `def3` | +13 | **ghost** | writes `ghost0_active` |
| `def4` | +12 | the special actor named by `tbl_ScreenKind` | `PickSactorKind` |
| `def5` | +11 | **spider** | seed `$98` |

The rate mask is the reciprocal of the rate: `$FF` is rare, `$00` fires every
frame. An amount of `$FF` means the budget never runs out.

## Kinds 10 and 11 can never appear

`tbl_SactorToughness` is `$00` for kinds 10 and 11, and `$C4`-`$FE` for every
other kind. That value is written straight into `sactor_damage` when the actor
is placed (`f6:$65D4`), and the per-frame walk over the four special-actor slots
begins:

    LDA sactor_damage,X
    BEQ skip                  ; a zero reads as an empty slot

So an actor of either kind is placed and then ignored on the very next frame.
Both kinds have artwork -- `dat_6440` gives kind 10 the heads `$90 $92 $94 $96`
and kind 11 `$B6`/`$BE`, and both have the normal body base `$50` -- but neither
can exist in play.

Two rooms ask for kind 10: `$46` and `$4F`. `$46` also has a bat budget, so
something still moves there. **`$4F` has no other cast at all**, which makes it
the one room in the game that is permanently, unintentionally empty.

## The wolf: def2's own slot

The wolf is not an ordinary actor. `def2` does not use the eight-slot array at
all -- it drives a single wolf through its own state:

| | |
|---|---|
| `$1FC6` | long position |
| `$1FC7` | cross position |
| `$1FC8` | current animation frame |
| `$1FC9` | state: 0 none, 1 alive, 2 the barn variant, `$40` struck, negative = dying |
| `$1FCA` | animation counter |

Only one exists at a time -- placement returns early unless `$1FC9` is zero.

It **enters from the right edge** (`$1FC6 = $C0`) at the player's own height
(`player_pos_cross - 3`), then runs left one unit a frame plus `world_drift`,
cycling three frames from `dat_5B8B` (`00 00 01 01 01 01 02 02`) -- the same
three frames the bestiary records for the wolf. Reaching the left edge clears
`$1FC9` and frees the slot.

Player shots test against a 16-unit box around it (`f6:$5973`), award through
`sub_D030` with `$0A`, and play effect `$0C`. Touching it sets `$1FC9 = $40` and
calls `sub_54DE` with 3.

**The barn is special**, in two ways.

Its header gives the wolf an **unlimited amount at rate mask `$01`** -- one in
two eligible frames, the fastest in the game. Everywhere else the budget is one
or two wolves at masks of `$0F` to `$7F`. That is why the barn pours them out
while other rooms send one.

And on `screen_kind_idx == $15` the state becomes 2, a variant that re-reads
`player_pos_cross` every frame -- it **tracks you vertically** -- and covers an
extra unit per frame.

A hit sets `X = $F5`, the dying state, *unless* the wolf is the barn variant and
`weapon_level` is 0:

    LDX #$F5
    LDA $1FC9 : CMP #$02 : BNE store    ; not the barn variant -> dies
    LDA weapon_level      : BNE store   ; anything but the knife -> dies
      LDX #$01                          ; knife on a barn wolf -> demoted to
    store: STX $1FC9                    ; the ordinary variant, still alive

So the knife **downgrades** a barn wolf to a plain one rather than bouncing off
it; a second knife hit then kills, since the state-2 test no longer matches.
Every other weapon kills either variant outright.

This is a hand-written exception, not a damage threshold. The knife is
`weapon_level` 0 and adds nothing to any accumulator, so it can only ever kill
things that die on a single hit regardless of damage -- the wolf, the bat, the
crow. The barn variant is the one case in the game where a specific actor is
coded to survive it.

## Each boss room maxes out a different threat

All three bosses are immune to the knife, and not by anything boss-specific:
`BossVsProjectiles` is shared, and its damage step is `LDA weapon_level / BEQ`
(`b5:$B515`), so a level-0 weapon simply skips the `DEC boss_health`. The Ram is
not special here.

What is special is the room in front of each one:

| room | boss | its extreme |
|---|---|---|
| `$15` barn | Ram | **wolves, unlimited, mask `$01`** -- the fastest sustained spawn in the game, plus the only vertically-tracking wolf |
| `$1E` crypt | Skull | **ghosts, unlimited, mask `$0F`** -- ghosts take `weapon_level + 1`, so the knife *does* kill them, one hit at a time |
| `$3C` | Dr Evil | **throw mask `$01`** -- one projectile per two frames, the densest in the game |

Three different mechanisms, each pushed to its limit, each in the room guarding a
boss the knife cannot hurt.

## Only one boss is reachable with the knife

The other two are shut off earlier, by gates rather than by difficulty. Both
gating rooms are **one segment wide, so they do not scroll** -- there is nowhere
to retreat to -- and both hold a **pending** item, which only appears once the
room has been cleared:

| room | holds | cast that must die | knife? |
|---|---|---|---|
| `$4A` | the **crypt key**, pending | random kinds 0-3 | no -- these need accumulated damage |
| `$3B` | the **screen gate**, pending | **8 Dr Evil zombies**, the `$C4` seed | no |

No crypt key means no Skull. No screen gate means the top rows of `$3B` stay
solid, and Dr Evil's room is never reached. Neither gate is a weapon check in
code; both are ordinary clear-the-room conditions that a zero-damage weapon
simply cannot satisfy.

That leaves the Ram as **the only boss a knife-only player can stand in front
of** -- and the barn is the room tuned hardest against them: unlimited wolves at
the fastest sustained rate in the game, the only variant that tracks the player
vertically, and the single bespoke exception in the whole ROM that makes an
actor survive a knife hit.

So the pattern is not "each approach is hard". Two routes are closed outright,
and the one that stays open is the one carrying the hand-written anti-knife
code.

### How the wolf is drawn

`$1FC8` holds a frame number, and `f6:$5BB6` turns it into a picture the same
way everything else in the game does:

    LDA $1FC6 : SEC : SBC #$20 : STA $6C     ; long base
    LDA $1FC7 :                  STA $6D     ; cross base
    LDA $1FC8 : ORA #$40
    JMP sub_4329                             ; the composite-record renderer

So the wolf's frames are **composite records `$40`-`$4E`** in `dat_455C`, the
same table the player and the special actors use. There was never a separate
wolf drawing path; the frame number is just an index with `$40` set.

| `$1FC8` | record | |
|---|---|---|
| `0`-`2` | `$40`-`$42` | the run cycle, from `dat_5B8B` |
| `$03`-`$0C` | `$43`-`$4C` | the death sequence, from `dat_5B93` |
| `$0D`, `$0E` | `$4D`, `$4E` | the two idle frames, from `dat_5B9D` |

All fifteen are two-part composites on page `$E0`, except the death frames,
which are one part each. Rendered, `$40`-`$42` are a three-frame run cycle in
profile -- which is what the bestiary records as "3 frames, 24 px" from the
sprite side.

`sub_4329` also takes a flash override in `$69`: non-zero forces every part to
palette 6, the randomised one, which is how a struck actor strobes.

## One table draws everything

`dat_455C` is the single mechanism behind three things that look unrelated:

* the **special actors** -- body base plus facing and walk counter;
* the **wolf** -- `$1FC8 | $40`;
* the **player**, including both undead forms -- `$5E`.

Each was chased down its own path and each ended at the same routine. Anything
that still looks like an unexplained sprite index is worth trying here first.
