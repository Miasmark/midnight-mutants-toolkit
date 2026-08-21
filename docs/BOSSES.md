# Midnight Mutants -- boss fights

A boss fight is a separate mode. When `mode_flag` (`$1E9D`) is non-zero the main
loop pages in bank 5 and hands off to it, and the normal area load, terrain grid
and actor arrays are bypassed. That is why boss arenas do not appear in
`AREAS.md`: they are not rooms.

## The bank 5 interface

Bank 5 opens with a six-entry jump table. Every entry is called from bank 6:

| vector | target | called from | what |
|---|---|---|---|
| `$B000` | `$B013` | `f6:$4B37` | arena setup: clears `$2400`-`$26E8`, zeroes `item_type` |
| `$B003` | `$B28B` | `f6:$4CFC` | per-fight dispatch |
| `$B006` | `$B45C` | `f6:$52E0` | **the per-frame tick** |
| `$B009` | `$B4B8` | `f6:$5418` | position/pointer computation from `$1E9E`/`$1E9F` |
| `$B00C` | `$B962` | `f6:$4096` | the arena's actor draw loop, from the NMI path |
| `$B00F` | `$B6AC` | `f6:$685A` | the status-bar message selector |

Three of these are labelled `dat0_*` or `sub3_*` in the listings: the
disassembler resolves the `$8000` window to the wrong bank at those call sites
and never follows them, so most of bank 5 remains untraced. See the tooling note
at the end.

## The boss takes exactly one point, and never from the knife

`b5:$B4FE`, inside the projectile loop:

    LDA $1EA7
    CMP $0077,Y          ; against proj_pos_cross
    BCC next
    LDA #$0A : STA $1EA8 ; hit flash
    LDA #$10 : STA sfx_request
    LDA #$FF : STA $007A,Y   ; kill the projectile
    LDA weapon_level
    BEQ next             ; level 0 -- the knife -- does nothing at all
    LDA boss_health
    BEQ next
    DEC boss_health      ; exactly 1, whatever the weapon
    BNE next
    LDA #$20 : STA $1EA0 ; defeated
    LDA #$07 : JSR $4006

So the axe, blaster and mega blaster are identical against a boss -- the weapon
level is tested only for being non-zero. This is the third of the game's three
damage rules, and the only one that had been inferred from play rather than read
until now.

`boss_health` (`$1EA3`) is seeded at `$B070` from the boss's own record during
setup, alongside `$1EA9` and the player's starting position.

## The player is driven by a separate control loop

`b5:$B45C`, the per-frame tick, reads the joystick from `$55` and moves the
player directly -- the normal movement code in bank 6 is not running:

| bit clear | facing (`$5F`) | effect |
|---|---|---|
| 0 | 1 | `DEC player_pos_cross` |
| 1 | 0 | `INC player_pos_cross` |
| 2 | 2 | `DEC player_pos_long` |
| 3 | 3 | `INC player_pos_long` |

It also calls `$B687` when `sel_item` (`$C8`) is non-zero, which is how items
are used mid-fight.

## The arena draws from its own table

`b5:$B962`, called every frame from the NMI path, walks the eight ordinary actor
slots and builds display entries directly:

* `$1EAC` supplies the graphics page for all of them
* `actor_field_B7,Y` supplies the palette-and-width byte
* the sprite is `dat_BB38[(frame_ctr & 7) | actor_mode]`

So during a fight the actors animate from a single table indexed by the frame
counter ORed with the mode, rather than through the composite records used in
the walkable world.

## Setting up a fight

`b5:$B013` takes the boss number in `A` and reads a **32-byte setup record**,
via a pointer table at `dat5_B19F`. There are three bosses, numbered **1, 2 and
3**; slot 0 is a null pointer.

| offset | |
|---|---|
| +0 | palette set index (`$1EA2`), selects a 40-byte block via `dat5_B207` |
| +1 | arena graphics page |
| +2, +3 | `boss_box_lo` / `boss_box_hi` |
| +4, +5 | `boss_box_cross_lo` / `boss_box_cross_hi` |
| +6 | `boss_health` |
| +7 | `boss_fire_dir` |
| +8, +9 | the player's starting long / cross position |
| +10..+13 | `$1EC2`, `$1EC3`, `$1EC1`, `$1EC4` |
| +14 | `$1EAA`, the stage counter's starting value -- `$00` for all three |
| +16..+31 | four groups of `(src lo, src hi, offset, row)` drawn by `$B141` |

Fields +6 through +9 are **skipped when `$1F9D` is non-zero**, which is the
re-entry path: health and start position survive, so returning to a fight does
not reset it.

Each group in the tail blits into the arena character map at
`dat5_B195[row] | dat5_B19A[row] << 8`, giving rows at `$2400`, `$2464`,
`$24C8`, `$252C` and `$2590` -- a stride of 100 bytes.

`ArenaBlit` (`b5:$B141`) reads a **four-byte header** off the source first: the
first two bytes are the width and height in characters. It then walks `height`
rows of `width` bytes, advancing the destination by 100 each time.

## There is no arena

Exactly one group is populated per boss, and what it blits is not scenery -- it
is **the boss itself**, one large portrait pasted straight into the character
map:

| boss | source | size | drawn at |
|---|---|---|---|
| 1 Skull | `b5:$9000` | 9 x 9 characters | row 0, column 33 |
| 2 Ram | `b5:$9055` | 16 x 9 | row 0, column 9 |
| 3 Dr Evil | `b5:$90E9` | 20 x 10 | row 0, column 30 |

Everything else on screen is background. That is why a fight bypasses the area
loader completely, and why `AREAS.md` has 76 rooms and no arenas: there is no
room to describe, only a picture and the fight logic running over it.

Bank 5's 12K of "data" is now accounted for -- character sets at CHARBASE `$80`
and `$A0`, these three tilemaps at `$9000`, the boss music in the tail, and code
from `$B000`.

**Dr Evil's portrait has pointed ears on both sides of the face.** His hitbox
alternates between two windows on the long axis roughly 56 units apart, and the
picture is what that mechanic is aiming at.

`tools/arenas.py` renders all three from the ROM, and the editor edits
them cell by cell -- the picture is the only thing a fight draws, so it is
the whole of a boss's appearance.

The hitbox is the record's `+2`..`+5`, copied to `$1EA4`-`$1EA7` by the
setup walk at `b5:$B04E` and tested by `BossVsProjectiles`. Those four
bytes are editable; because the horizontal mapping is only derivable for
Dr Evil, the editor works in shifts from the stock value rather than in
screen coordinates.

## Each boss is hand-written

`sub5_B28B` is the per-frame update, and it is a three-way dispatch on
`mode_flag` -- boss 1 to `$B2A7`, boss 2 to `$B351`, boss 3 to `$B3D4`. There is
no shared movement engine and no data-driven behaviour table: each boss is its
own routine.

What they share is the shape:

1. `boss_health == 0` jumps to the death path at `$B55C`
2. movement comes from **`dat_DD00`**, indexed by `$1EA0`
3. `BossVsProjectiles` (`$B4D7`)
4. an attack roll gated by a mask
5. the stage counter `$1EAA` advances, clamped at `$0F`
6. palette 7 is written with three hardcoded colours

`dat_DD00` is the sine table already driving the zombie head bob and the flying
actors' drift. The bosses are its **fourth** consumer -- boss 1 reads it as a
vertical bob (`(sine >> 2) + 8`), boss 3 feeds it straight into `boss_pos`, and
boss 2 samples it twice per frame.

## Boss 3 is Dr. Evil, and his weak spot alternates

Boss 3 is the only one that moves its own hitbox, which identifies him. At
`b5:$B3E5` he tests bit 7 of `$0045` and picks one of two positions on the long
axis:

    LDA $45 : BPL right
      LDA #$00 : STA $5B      ; left
      LDA #$2E : BNE store
    right:
      LDA #$01 : STA $5B
      LDA #$66
    store:
      STA boss_box_lo
      CLC : ADC #$0A : STA boss_box_hi

Two ten-unit windows, at `$2E`-`$38` and `$66`-`$70`, 56 units apart. Since
`BossVsProjectiles` tests a shot against exactly that box, **only the current
side can be hit** -- these are the ears, and the vulnerable one changes.

`$0045` increments every other frame (`f6:$40B4`), so bit 7 flips every 256
frames: **the weak spot swaps roughly every 4.3 seconds.**

### He fires from whichever ear is currently weak

The same branch stores 0 or 1 into `$5B`, and the fire routine reads it back at
`b5:$BAEB` to place the shot:

| `$45` bit 7 | `$5B` | weak spot | shot spawns at |
|---|---|---|---|
| set | 0 | `$2E`-`$38` | `boss_pos + $34` |
| clear | 1 | `$66`-`$70` | `boss_pos + $66` |

So the projectile always comes out of the ear you can currently damage -- the
tell and the threat are the same thing.

**`$5B` is `player_x_lo` everywhere else in the game.** During a boss fight it
is reused as the weak-spot side flag and has nothing to do with the player. The
disassembly labels it from its normal-play role, which is misleading here.

The shot starts at cross `$50` with `vel_cross = (boss_stage >> 2) + 1`, so it
also **falls faster as the fight wears on**, and takes a long velocity from
`dat5_BB38` = `80 80 80 80 00 00 01 FF`. Half those entries are `$80`, the
sine-wiggle marker `sub5_B9A4` checks for, so half his shots weave on the way
down instead of dropping straight.

His fire mask (`dat5_B44C`) ramps in threes rather than pairs:

    3F 3F 3F 1F 1F 1F 0F 0F 0F 07 07 07 03 03 00 00

### The crawling bug

Dr. Evil has a second attack that is not a shot at all. The first half of
`DrEvilFire` fills **actor slot 7**:

    actor_pos_cross[7] = player_pos_cross    ; enters at your height
    actor_vel_cross[7] = 0                   ; never rises or falls
    boss_stage & 1 ?  pos_long = $C0, vel_long = $FF   ; from the right
                   :  pos_long = $00, vel_long = $01   ; from the left
    actor_mode[7]  = $30 or $18              ; faces the way it travels

`vel_cross = 0` is what makes it crawl dead level across the arena, and
`vel_long = +/-1` makes it slow -- one unit a frame against `2` for an ordinary
shot. `BossActorMove` only applies its sine wiggle when `vel_long == $80`, so
the bug travels perfectly straight while half his ear shots weave.

It enters at **your** cross position at the moment it spawns, so it is aimed
when it appears and then commits; moving after that is what avoids it. Which
side it comes from is `boss_stage & 1`, so it switches ends each time the
difficulty stage advances rather than at random.

**It is a contact hazard, not a projectile.** `sub5_BB90` walks all eight actor
slots and tests each against the player, so the bug hurts on touch exactly like
a shot does -- it is consumed on contact, sets a 20-frame cooldown in
`terrain_timer`, and costs the same health. That is why it behaves like one.

Spawning is gated three ways: the fire-rate mask must pass, `tick_fast & $0F`
must be zero, and slot 7 must be free. **The bug takes priority over the ear
shot** -- when one spawns the routine returns immediately, so no ear shot is
fired that frame.

## Contact damage is per boss

`sub5_BB90` reads the damage from a three-entry table at `$BBFD` indexed by
`mode_flag`:

| boss 1 | boss 2 | boss 3 (Dr. Evil) |
|---|---|---|
| `$0A` | `$05` | `$09` |

Touching boss 2 costs half what the other two do. On contact the game also picks
a knockback from `dat5_BC00` / `dat5_BC0C` using `mode_flag * 4 + (Random & 3)`,
so the direction you are thrown is one of four per boss.

### Dr. Evil also costs blood purity

`CPY #$03 / JSR sub_D039` is the extra call only he makes, and `sub_D039`
resolves to `DrainBloodPurity` at `f7:$D41A`:

    LDA death_state  : BNE done      ; already dead
    LDA itm_heart    : BNE done      ; holding the heart -- nothing happens
    LDA blood_purity : BEQ done      ; floor at zero, never wraps
    DEC blood_purity

So touching Dr. Evil costs health **and** a point of purity, where the other two
bosses cost only health. Since purity reaching zero is a death condition in its
own right (`CheckDeathCondition`), that is a second way he can kill you.

**The heart cancels it outright.** It is not a reduction -- a non-zero
`itm_heart` returns before the `DEC` -- and the check sits inside the shared
drain routine, so **all 17 call sites in the game are cancelled by the same
test**. Carrying the heart into this fight removes the entire purity threat, so
the advice to collect it first is exactly right.

## The bosses ramp up

This is what `$1EAA` is for. The attack is a random roll masked by
`dat5_B3C0[$1EAA]`:

    dat5_B3C0 = 3F 1F 1F 1F 0F 0F 07 07 03 03 02 02 01 00 00 00

and `sub5_B9EF` fires only when `Random AND mask` comes out zero:

    STA $40 : JSR Random : AND $40 : BNE dont_fire

So the mask is the reciprocal of the fire rate. `$1EAA` starts at 0 and climbs
one step roughly every 17 seconds (`$1EAB` counts 1 per 4 frames and carries at
256), and the mask halves as it goes: **1-in-64 at the start, and `$00` --
firing every single frame -- by stage 13.** The longer a fight drags on, the
denser the attack becomes, until it is continuous.

**Being hit makes a boss angrier.** When `boss_flash` is set the index is
advanced by five before the lookup, jumping e.g. `$3F` to `$0F` -- four times the
fire rate while the boss is flashing from a hit.

A shot spawns in actor slot 7 at `boss_pos + $4B`, cross `boss_box_cross_lo + 4`,
with `vel_long = 2` and a cross velocity picked randomly from
`dat5_BA3C` = `00 01 02 03 00 08 09 0A` -- eight spread directions. It also sets
`$1EAC = $A0`, which is the graphics page the arena renderer then uses for every
actor slot.

## The RAM, resolved

| | |
|---|---|
| `$1EA0` | movement phase, indexes `dat_DD00` |
| `$1EA2` | palette set index |
| `$1EA7` | `boss_box_cross_hi` (from setup +5) |
| `$1EA9` | `boss_fire_dir` (from setup +7) |
| `$1EAA` | **stage counter**, 0-15, the difficulty ramp |
| `$1EAB` | sub-counter feeding `$1EAA` |
| `$1EAC` | actor graphics page, set to `$A0` when the boss fires |

## Bank 5 opens with a jump table

`$B006`-`$B011` holds three `JMP`s reached only through the vector table, so a
recursive-descent tracer emits them as data and never follows them. `$B45C`,
`$B4B8` and `$B962` have to be declared as entry points before any of the fight
code is reachable.

The music envelope handlers behind `JMP (music_env_vec)` are the same shape:
a jump the tracer cannot see is a jump it cannot follow, and the fix in both
cases is to declare the target.
