# Midnight Mutants -- item audit

Every inventory slot, and every place in the cartridge that reads or writes it.

Method: scan all eight banks for each opcode that can carry an absolute operand,
matched against `$1F3D + n`, plus every `LDA sel_item / CMP #n` pair. This bounds
the answer rather than extending it: following gameplay paths can only add
effects one at a time and never establishes that the list is complete.

One hit was a false positive: `f7:$DE60` sits inside a `.byte` block where
`2D 48 1F` reads as `AND $1F48` but is graphics data. Anything flagged here is
checked against the disassembly before being believed.

## Summary

| item | slot | code refs | what reads it |
|---|---|---|---|
| cross | `$1F3E` | 7 + 1 selected | eight distinct effects -- see ACTORS.md |
| crypt key | `$1F3F` | 2 + 1 selected | Grampa's messages; terrain `$85` when selected |
| necklace | `$1F40` | 2 + 1 selected | boss status line; +4 purity drains; water walk when selected |
| heart | `$1F41` | 2 | Grampa's messages; blood-purity immunity |
| plasmic pumpkin | `$1F42` | 1 + 1 selected | its own spawn check; the win when selected |
| red potion | `$1F43` | 3 | use, auto-use, pickup |
| blue potion | `$1F44` | 3 | use, auto-use, boss status line |
| **diamond** | `$1F45` | **0** | nothing ever reads it |
| lantern | `$1F46` | 2 | Grampa's messages; area darkness |
| knife | `$1F49` | 1 | Grampa's messages only |
| axe | `$1F4A` | 1 | Grampa's messages only |
| blaster | `$1F4B` | 1 | Grampa's messages only |
| **mega blaster** | `$1F4C` | **0** | nothing ever reads it |

## Two slots are write-only

`$1F45` (diamond) and `$1F4C` (mega blaster) are incremented on pickup and never
read again. Neither is a bug:

* the diamond's effect happens *at* pickup -- `f6:$520F` adds 8 to `hp_max` and
  refills, driven by `item_type`, not by the counter. That raised `hp_max` is
  then read by the death path: revival needs `hp_max >= $30`, which from a base
  of `$27` takes **two diamonds**. See `PLAYER.md`;
* the weapons work through `weapon_level` (`$86`) and its rate companion
  (`$88`), which `CollectItem` sets for item numbers `$0C`-`$0F`. The inventory
  counter exists so the icon can be drawn on the Grampa screen.

The same is true of the other three weapons in all but one respect: knife, axe
and blaster are each read exactly once, and only by Grampa's message selector.
Carrying a weapon changes what he says; it does not change what the weapon does.

## Grampa's advice is item-gated

`b0:$A3E2`-`$A460` is a chain of item tests that picks his message index:

    heart -> knife -> cross -> axe -> crypt key -> blaster -> lantern

Each test that passes selects a different hint, so his dialogue tracks progress
through the inventory rather than through `boss_flags`.

## Selected-item effects

Only five items do anything when *selected* on the Grampa screen, which is a
separate mechanism from merely owning them:

| selected | effect |
|---|---|
| cross `$01` | immune to contact blood loss (`f6:$5FA7`) |
| crypt key `$02` | terrain `$85` fires `forced_msg $81` (`f6:$56E2`) |
| necklace `$03` | water walk, room `$01` only (`f7:$D0C5`) |
| plasmic pumpkin `$05` | terrain `$EF` wins the game (`f6:$575C`) |

Searching only for reads of the inventory counter misses these entirely: an item
can be inert as a counter and still do something when selected.

**Only slots `$01`-`$07` can be selected at all.** The Grampa screen's cursor
advance at `b0:$A533` masks with `AND #$07`, so the lantern (`$09`) and the four
weapons (`$0C`-`$0F`) are unreachable by it. That is not an oversight: those
items act by being owned. The lantern clears `area_is_dark`, and the weapons set
`weapon_level`, which is what the fire path reads. The cursor also skips any
slot whose counter is zero, so it only ever lands on something carried.

## Blood purity and the heart

Every purity loss in the game goes through one routine, `DrainBloodPurity`
(`f7:$D41A`, reached via the `sub_D039` trampoline), and it drains exactly one
point per call:

    LDA death_state  : BNE done
    LDA itm_heart    : BNE done      ; <- the whole mechanic
    LDA blood_purity : BEQ done      ; floors at zero
    DEC blood_purity

**The heart is a hard gate, not a reduction.** A non-zero count returns before
the `DEC`, and because the test lives inside the shared routine it cancels
*every* purity loss in the game -- all 17 call sites -- rather than any
particular one.

### Larger losses are written as repeated calls

There is no "drain N" argument. A bigger loss is simply more `JSR`s in a row,
and a conditional entry point partway down the ladder scales it:

| site | purity | |
|---|---|---|
| `f6:$5FAD` | 1 or 2 | `sel_item` = cross is fully immune; merely *owning* the cross skips the second call |
| `f6:$5FE6` | 2 | plus health damage of `(boss_flags << 1) + 2`, so it scales with progress |
| `f6:$6016` | 5 or 9 | five always; **four more if `itm_necklace` is held** |
| `f6:$6728` | 2 | special-actor contact |
| `b5:$BBE1` | 1 | Dr. Evil contact only |

### The ladder is what makes the cost editable

There is no argument to change, but a call is three bytes and so are three
`NOP`s, so a point can be removed from any site without moving anything. All
seven runs:

| site | calls | |
|---|---|---|
| `f6:$5B69` | 1 | the periodic bleed, one point every fourth tick |
| `f6:$5FAD` | 1 | enemy contact; skipped while the cross is selected |
| `f6:$5FB5` | 1 | its second point; skipped if you own the cross |
| `f6:$5FE6` | 2 | tough-actor contact |
| `f6:$6016` | **9** | enemy projectile |
| `f6:$6728` | 2 | special-actor contact |
| `b5:$BBE1` | 1 | Dr. Evil contact |

The projectile ladder has a second lever. Its nine calls run from `$6016`, and
the necklace test picks which rung execution starts on:

```
6011  AD 40 1F   LDA itm_necklace
6014  F0 0C      BEQ +12          -> $6022, five rungs left
6016  20 39 D0   JSR              -> holding it, all nine
```

The branch operand is the entry point, so **the cost without the necklace is one
byte**: `$00` enters at the top for nine, `$0C` skips four for five, `$1B` skips
the lot for none.

And the test itself can go. Replacing `LDA itm_necklace` with `LDA #$00 / NOP`
-- the same three bytes -- leaves Z always set, so the branch is always taken
and the necklace stops costing anything extra. Nothing else depends on what that
`LDA` fetched: `sub_D039` is a `JMP` into `DrainBloodPurity`, which loads the
accumulator on its first instruction.

### The necklace penalty, and why it is hard to see

The `$6016` site is `sub_5FF6`, and the dispatcher at `f6:$5F6E` reaches it only
when `actor_mode` is **exactly `$FD`** -- the mode `SpawnEnemyProjectile` assigns
to a thrown enemy projectile. So this is the handler for *being hit by an enemy
shot*, not a water hazard.

Holding the necklace really does make it worse: `LDA itm_necklace / BEQ` enters
the ladder four calls early, so a hit costs **9 purity instead of 5**, on top of
6 health either way. There is no compensating benefit at this site.

Two things keep it out of sight:

* **The heart cancels it**, like every other drain. Any run carrying the heart
  never sees purity move at all.
* **Only 10 rooms of 76 have throwing enemies**, gated by `throw_enable`
  (`$1FCC`), which is loaded per area from header byte `+0F`.

To observe it you need a run *without* the heart, *with* the necklace, taking a
thrown hit in one of those rooms.

## Where items are, and item_type

Area header **+7** is `item_type`. The low seven bits are the item id; **bit 7
means the item is pending** -- present in the room but not drawn or collectable
until the room has been cleared. `DrawItemIcon` returns early on `BMI`, so a
pending item simply is not rendered. It is the same item waiting to appear, not
a separate class.

The id indexes the inventory directly: **slot = `$1F3D` + id**.

| id | item | rooms |
|---|---|---|
| `$01` | cross | `$14` |
| `$02` | crypt key | `$4A` (pending) |
| `$03` | necklace | `$12` |
| `$04` | heart | `$01` |
| `$06` | red potion | `$0C`, `$21`, `$4B` |
| `$07` | blue potion | `$0B`, `$15`, `$1E`, `$3C`, `$4D`, `$2E`, `$30` |
| `$08` | diamond | `$08`, `$0D`, `$0E`, `$11`, `$16`, `$33`, `$49`, and 7 more pending |
| `$09` | lantern | `$1B` |
| `$0B` | screen gate | `$3B` (pending) |
| `$0C` | **knife** | `$43` |
| `$0D` | **axe** | `$1D` |
| `$0E` | **blaster** | `$1C` (pending) |
| `$0F` | **mega blaster** | `$20` (pending) |

The four weapons are consecutive ids in the order you collect them, which is the
same order `weapon_level` runs in. The two strongest are both pending -- the
blaster and mega blaster only appear once their room is cleared.

Confirmed in play: `$43` knife, `$1D` axe, `$1C` blaster, `$20` mega blaster.
