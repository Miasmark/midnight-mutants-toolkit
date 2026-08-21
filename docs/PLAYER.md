# Midnight Mutants -- the player

## Input

`f7:$D101` is the only place the controller is read:

    LDA SWCHA
    LSR A x4        ; player 1 lives in the high nibble
    STA ram_0055

`$55` therefore holds four active-low direction bits: bit 0 up, 1 down, 2 left,
3 right.

The necklace's water walk is checked on the way in, not as a separate pass:
`sub_D0C0` tests `sel_item == $03` and the player's position, sets `ram_1FA9` to
`$FF` if the walk is permitted, and falls through into the read above.

## Movement is trial-then-commit

`f6:$5302` copies the live position into a trial copy --

| live | trial |
|---|---|
| `$59` cross | `$5D` |
| `$56`/`$57` long, 16-bit | `$5B`/`$5C` |

-- adjusts the trial, tests it against the terrain, and only then writes it back.

**One direction per frame, on the first attempt.** Each direction test ends with
`STX ram_0055` where X is `$0F`, setting every bit and so preventing any later
test from firing. Press up and right together and only the first is tried.

Diagonals are not discarded, though -- see the wall slide below.

**The axes move at different rates.** A direction steps the cross axis by one
every frame but the long axis only on alternate frames:

    DEC ram_005D            ; cross, every frame
    LDA ram_005D
    AND #$01
    BEQ skip
    INC ram_005B            ; long, every other frame

So walking "up" also drifts sideways at half speed. Movement is not
axis-aligned.

**The long axis is clamped** to `map_limit` (`$72`/`$73`) before the collision
test, which is what stops the player leaving the world at its far edge.

## Collision is per half-cell

`sub_55E3` decides whether the trial position is legal.

It first works out which diagonal half of the cell the player is standing in:

    ($5D + $0C) & $0F              sub-position across the cell
    (($5B - $18) & $07) * 2        plus sub-position along it
    compared against $10           -> $50 = 1 or 2

Then it looks the terrain up through `sub_D027` with the same offsets --
cross `+$0C`, long `-$18` -- and decides:

| terrain | result |
|---|---|
| `$00` | open, move allowed |
| bit 7 set | an event square: handled by `TerrainDispatch`, not blocked here |
| class `$03` | solid, blocked |
| class `$01` or `$02` | blocked **only if it matches `$50`** |

That is what the `/` and `:` glyphs in `build/maps/` mean: each blocks one
diagonal half of its cell, and whether you are stopped depends on which half you
are entering from. The `+$0C` and `-$18` offsets are the same constants the map
tools use, which were originally calibrated by fitting item positions against
observed play -- the code confirms them.

If the first test fails, `sub_5521` runs and the test is repeated. That routine
is the **wall slide**, and it is where diagonal input is actually handled.

The raw joystick byte was saved to `$1FDB` at `f6:$5319` *before* `$55` was
masked, so the retry can see what was really pressed:

| `$1FDB` | bits clear | meaning |
|---|---|---|
| `$0E` `$0D` `$0B` `$07` | one | up, down, left, right |
| `$06` `$05` `$09` `$0A` | **two** | up-right, down-right, down-left, up-left |

A blocked diagonal resolves to a single-axis slide. Pressing up and right into
something that blocks upward movement sets facing to right and steps the long
axis alone, so the player slides along the obstruction instead of stopping.

The retry also writes `$0F` into `$50`, the half-cell indicator, so the second
collision test cannot be blocked by the diagonal-half rule that rejected the
first attempt.

## The commit

On success, `f6:$53BD` writes the trial back:

    $5D -> $59      cross
    $5B -> $56      long low   <-- this is screen_idx
    $5C -> $57      long high

`screen_idx` is not a separate concept: it *is* the player's long-axis position,
written here every time a step is taken. That is why room identity is read off
the player's coordinates rather than stored, and why the exit segment is
`(world position - $18) / 160`.

On failure, `$62` -- the "moving" flag -- is cleared, which stops the walk
animation.

## During a boss fight

None of the above runs. `mode_flag` diverts the main loop into bank 5, whose
per-frame tick at `b5:$B45C` reads `$55` directly and moves the player with no
terrain test at all. See `BOSSES.md`.

## The two buttons

`f7:$D0B1` latches both, once per frame:

    LDA INPT1 : AND #$80 : STA ram_1FC0     ; fire / use
    LDA INPT0 : AND #$80 : STA ram_1FC2     ; the Grampa screen

## Firing

`sub_4FE2` runs the fire path, and its first decision is not about weapons:

    LDA death_state : BNE done              ; dead, no firing
    LDA ram_1FC0    : BEQ done              ; button not held
    LDA sel_item
    BEQ no_item
      JSR sub_506C                          ; an item IS selected -> use it
      JMP done                              ; ...and the weapon never fires

So **selecting an item repurposes the fire button.** With anything selected on
the Grampa screen the button uses that item; only with the cursor on slot 0 does
it shoot.

With no item selected:

    LDA weapon_level : BMI done             ; no weapon at all
    LDA ram_0087     : BNE done             ; still cooling down
    find a slot in proj_type where bit 7 is set   ; 3 slots, bit 7 = free

and the spawn fills it:

| field | value |
|---|---|
| `proj_type` `$7A` | `weapon_level * 4 + facing` |
| `proj_gfx` `$83` | `dat_4FD2[type]` |
| `$7D` | 0 -- the animation phase, reset |
| `proj_pos_long` `$74` | `player_pos_long + dat_5064[weapon]` = `+0, +2, +3, +3` |
| `proj_pos_cross` `$77` | `player_pos_cross + dat_5068[weapon]` = `+0, +0, +1, +2` |
| `$87` | reloaded from `$88`, the weapon's rate |
| `sfx_request` | `weapon_level + 1` -- a different sound per weapon |

During a boss fight the direction comes from `$1EA9` rather than the player's
facing, so shots go where the fight wants them.

## The Grampa screen

It lives in bank 0. The cursor advance is `sub0_A533`:

    TXA : CLC : ADC sel_item
    AND #$07                     ; wraps at 8
    STA sel_item
    TAY
    BEQ done                     ; slot 0 = nothing selected
    LDA inventory,Y
    BEQ retry                    ; not owned -- skip to the next

Two consequences fall out of that mask:

* **Only slots 0-7 can ever be selected.** The lantern (`$09`), knife (`$0C`),
  axe (`$0D`), blaster (`$0E`) and mega blaster (`$0F`) are unreachable by the
  cursor, which is exactly why they act by being *owned* rather than selected --
  the lantern clears darkness, the weapons drive `weapon_level`.
* **The cursor skips what you do not have**, looping until it finds an owned
  item or lands back on slot 0.

That accounts for every selected-item effect found in `ITEMS.md`: cross `$01`,
crypt key `$02`, necklace `$03`, pumpkin `$05`, and the two potions `$06`/`$07`
through `UseSelectedItem`. Nothing outside `$01`-`$07` could have one.

### Entering it

`b0:$A19E`, the third entry in bank 0's jump table, is the screen itself. It

* clears the display list at `$2000`
* sets `CTRL` to `$40` and `CHARBASE` to `$80`
* pages bank 0 into the window and blanks `$2400`/`$2500` with `$20`, the space
  character
* copies `dat_D800` and `dat_D8E8` from bank 7 into `$2600`/`$26E8`
* waits for button 2 to be released, then points `DPPL`/`DPPH` at `$2600`

so the screen has its own display list entirely separate from the play area's
double-buffered pair.

### Which message Grampa gives

`sub0_A32B` picks it, as a priority chain -- the first match wins:

| test | message |
|---|---|
| `forced_msg` (`$1F9E`) non-zero | `(forced_msg & $7F) \| $20` -- the story screens |
| `undead_flag` (`$1FD5`) non-zero | `$0C`, the undead ending |
| `win_flag` (`$1FCD`) non-zero and positive | `$0D`, the win |
| `death_state` (`$8B`) non-zero | the revive path, which also draws a bar from `hp_max` |
| otherwise | the item-gated advice chain at `$A3E2` |

The index then selects a text pointer from `dat0_A608` (low) and `dat0_A63A`
(high), 50 entries.

That advice chain is the one described in `ITEMS.md`: heart, knife, cross, axe,
crypt key, blaster, lantern, each test that passes choosing a different hint. So
what Grampa says tracks the inventory, except when a story trigger, an ending or
death overrides it.

The screen runs its own frame loop, including a second copy of the palette-6
randomiser at `b0:$A485` identical to the one in the main loop, so the damage
flash strobes here too. Holding the console reset switch (`SWCHB` bit 0) from
this screen jumps to `$FF00`.

## The screen's layout: dat_D800

`dat_D800` is `tbl_MsgScreenDLL`, a **display list list**. `b0:$A1C3` copies it
to `$2600` and `dat_D8E8` to `$26E8` in one 256-iteration loop, then points
MARIA at it with `DPPH = $26`. Three bytes per zone: height-1 in the low nibble
of the first, then the display list address high and low.

| zones | height | list | what |
|---|---|---|---|
| 0-3 | 8, 8, 4, 3 | `$1F36` | blank -- one empty list shared by every blank zone |
| 4 | 16 | `$2000` | blanked on entry (`$A19E` zeroes `$2000`/`$2001`), so empty |
| 5 | 5 | `$1F36` | blank |
| **6-21** | **8 each** | `$2663` + row&times;15 | **the 16 message rows**, 128 scanlines |
| 22 | 5 | `$1F36` | blank |
| 23 | 16 | `$2000` | empty, as zone 4 |
| 24+ | 8 | `$1F36` | blank |

Rows 0-8 come from `dat_D800`; row 9 onward starts at `$26EA`, which is why
`dat_D8E8` exists as a second block.

### A row

Each row's list is 15 bytes: three 4-byte headers and a terminator. All 16 rows
have the same shape.

    entry 1   16 bytes of art, palette 7, x $00
    entry 2   16 bytes of art, palette 1, x $00     <- same x, overlaid
    entry 3   the character map, palette 3, x $0A
    then a header whose width byte is 0, ending the list

**Entry 3 is the text.** It reads `$2400 + row * 22`, confirmed for all 16 rows,
so the message area is **16 rows of 22 characters** in the character map that
`GrampaPickMessage` fills.

**Entries 1 and 2 are the portrait**, drawn twice at the same position in two
palettes -- the same two-layer trick the actors use for head and body. The art
pages alternate `$98`, `$90`, `$98`, `$90` down the rows while the low byte
advances `$20` every second row, so the pair of rows at each step reads one
16-byte-wide slice out of the 4K image at `b0:$9000`-`$9FFF`.

`CTRL` is `$40` on this screen rather than the `$50` used in play: bit 4 clear,
so characters are **one byte** here and two bytes in the world.

## The player's own state

Set once at `f6:$4ADB`:

| | value | |
|---|---|---|
| `hp_cur` / `hp_max` (`$C5`/`$C6`) | `$27` = **39** | health |
| `blood_purity` (`$C4`) | `$64` = **100** | the second life bar |
| `revive_ok`, `win_flag`, `undead_flag`, `revive_timer` | 0 | |

Health is spent by contact and by hurting ground; purity by the 17 sites that
call `DrainBloodPurity`, all of which the heart cancels. They are independent
bars with independent consumers, and **either one reaching zero kills you** --
`CheckDeathCondition` (`f6:$4E70`) tests both and sets `death_state = $FF`. It
also sets `music_next_song = $0A`, which is how the funeral dirge starts.

## Dying of blood is not the same as dying of health

The death sequence at `f6:$4E8E` runs every eighth frame and forks on *which*
bar emptied:

**Purity reached zero.** `undead_flag` is set and the game ends -- there is no
resurrection from this. Which ending you get depends on one item:

    LDA blood_purity : BNE health_path
    LDX #$FF
    LDA itm_cross : BNE store    ; holding the cross
      LDX #$FE                   ; without it
    store: STX undead_flag

So the cross changes the ending itself, `$FF` against `$FE` -- the eighth and
least visible of its effects.

**Health reached zero, purity still above zero.** Two more conditions decide
whether Grampa can bring you back:

    LDA hp_max  : CMP #$30 : BCC no_revive
    LDA mode_flag           : BNE no_revive    ; not during a boss fight
    -> revive_ok = 1

Failing either falls through to `f6:$4ED5`, which jumps to `RESET`.

### Two diamonds are the price of a second life

`hp_max` starts at `$27` and the diamond is the only thing that raises it, by 8
each time (`f6:$520F`, observed in MAME as `$27` &rarr; `$2F` &rarr; `$37`).
Against the `$30` threshold:

| diamonds | `hp_max` | revivable |
|---|---|---|
| 0 | 39 | no |
| 1 | 47 | **no** |
| 2 | 55 | yes |

So the diamond's real function is not the health at all. `ITEMS.md` records that
nothing ever reads its inventory slot, and that is true -- but `hp_max` is read
here, and it is the gate on resurrection. **Fewer than two diamonds and death is
final**, whichever bar ran out.

That also explains the shape of the difficulty: the diamonds are scattered
across seven rooms, more than any other item, and half of them are pending.

## The two undead endings differ in one place only

`undead_flag` is read five times. Four of them test only whether it is non-zero:

* `b0:$A336` picks Grampa's message `$0C`, **"YOU'RE ONE OF THE UNDEAD"** --
  the same text either way;
* `f6:$5B30` forces the wolf's slot to state 1 and skips its normal update;
* `f6:$66F2` returns before the special-actor contact test, so nothing can
  touch you any more;
* `f6:$4AF1` clears it at a new game.

The fifth, `f6:$54FF`, is the only one that cares which value it holds:

    LDA undead_flag
    BEQ alive                  ; $5E = $0D, the ordinary player form
    CMP #$FF
    BNE no_cross
      LDA #$0E : STA $5E       ; died holding the cross: one fixed form
      RTS                      ; and returns early
    no_cross:
      LDA frame_ctr : ASL A : AND #$10 : CLC : ADC #$10
      STA $5E                  ; $10 or $20, alternating every 8 frames
      JMP sub_5413

`$5E` becomes the player's own sprite selector -- `f6:$439C` masks it and stores
it into `$1E37`, the graphics byte of the player's display slot -- so the flag
decides **what you are drawn as** once you are undead.

### What you turn into

`$5E` indexes `dat_455C`, the same composite-record table the actors use, so
each value is a page plus a list of parts. Resolving all three:

| `$5E` | page | parts | what it draws |
|---|---|---|---|
| `$0D` alive | `$C0` | cells `$88`, `$8C` | the player, in blue jeans |
| `$0E` cross | `$C0` | cells `$9C`, `$D0`, `$22` | a standing figure, still on the player's own page |
| `$10` / `$20` | **`$E0`** | cells `$10`/`$14` plus `$28` | **a bat**, two frames |

The `$E0` page is the creature page, not the player's -- and cells `$10` and
`$14` are exactly the two the bat's own sprite table `dat_5CE2` uses. **Dying of
blood loss without the cross turns you into a bat**, flapping between the same
two frames the game's bats fly with. Holding the cross leaves you standing on
the player's page instead.

Which is the whole game's premise landing in one byte: drained of blood, you
become the thing that drained you, unless you were carrying the cross.

The `$FF` path also returns before `sub_5413`, so the scroll and position update
stop as well.

Neither value can be reached with health: a blood death is always terminal, and
a health death goes to the revive path instead.
