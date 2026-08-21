# Midnight Mutants -- area headers

Every room the game defines, read from the ROM alone. The pointer
table is at `f7:$F32A + 2*screen_kind_idx`.

The table holds **80 entries** (`$F32A`-`$F3C9`), ending exactly
where the first header begins. **76 are real rooms**; the other 4
hold a null pointer and are not rooms at all: `$00`, `$3D`, `$3E`, `$3F`.

`dark` is cleared outright when the lantern (item `$09`) is held.


Five headers **overlap their neighbour**. Room `$10`'s record begins three bytes
inside room `$0F`'s last exit array: those bytes are simultaneously `$0F`'s
south-exit screens and `$10`'s stream, page and dark flag. The same is true
after rooms `$17`, `$1C`, `$20` and `$2E`. Nothing walks the block -- every
header is reached through the pointer table -- so the overlap costs nothing at
run time, but it means a header cannot be resized where it sits.

## Graphics pages

| page | rooms | count |
|---|---|---|
| `$01` | `$01` `$02` `$03` `$04` `$05` `$06` `$08` `$0B` `$0C` `$0D` `$0E` `$0F` `$13` `$16` `$36` `$39` `$3A` `$3B` `$3C` | 19 |
| `$02` | `$09` `$0A` `$10` `$11` `$18` `$19` `$1A` `$1B` `$30` `$31` `$32` `$33` `$34` `$35` `$37` `$38` | 16 |
| `$03` | `$12` `$14` `$15` `$1D` `$1E` | 5 |
| `$04` | `$17` `$1C` | 2 |
| `$07` | `$07` `$1F` `$20` `$21` `$22` `$23` `$24` `$25` `$26` `$27` `$28` `$29` `$2A` `$2B` `$2C` `$2D` `$2E` `$2F` | 18 |
| `$08` | `$40` `$41` `$42` `$43` `$44` `$45` `$46` `$47` `$48` `$49` `$4A` `$4B` `$4C` `$4D` `$4E` `$4F` | 16 |

## Darkness

| value | rooms |
|---|---|
| `$00` | 51 -- lit |
| `$07` | 17 -- dark without the lantern |
| `$FF` | 8 -- dark without the lantern |

## Rooms

| kind | header | page | stream | dark | map limit | exits |
|---|---|---|---|---|---|---|
| `$01` | `$F3CA` | `$01` | `$01` | `$00` | `$0136` | `$03`&rarr;`$0B`, `$04`&rarr;`$09`, `$05`&rarr;`$00` |
| `$02` | `$F3F2` | `$01` | `$02` | `$00` | `$0000` | `$06`&rarr;`$13` |
| `$03` | `$F410` | `$01` | `$02` | `$00` | `$013F` | `$13`&rarr;`$00`, `$13`&rarr;`$00`, `$07`&rarr;`$02` |
| `$04` | `$F438` | `$01` | `$04` | `$00` | `$0000` | `$08`&rarr;`$01` |
| `$05` | `$F456` | `$01` | `$03` | `$00` | `$0000` | `$08`&rarr;`$04` |
| `$06` | `$F474` | `$01` | `$04` | `$00` | `$0000` | `$08`&rarr;`$05` |
| `$07` | `$F492` | `$07` | `$0B` | `$07` | `$0000` | `$0F`&rarr;`$92` |
| `$08` | `$F4B0` | `$01` | `$03` | `$00` | `$00A0` | `$0C`&rarr;`$00`, `$0D`&rarr;`$13` |
| `$09` | `$F4D3` | `$02` | `$0E` | `$00` | `$0000` | `$2F`&rarr;`$0A` |
| `$0A` | `$F4F1` | `$02` | `$06` | `$00` | `$0000` | `$2F`&rarr;`$18` |
| `$0B` | `$F50F` | `$01` | `$0F` | `$00` | `$0000` | `$08`&rarr;`$0C` |
| `$0C` | `$F52D` | `$01` | `$0F` | `$00` | `$0000` | `$0B`&rarr;`$10` |
| `$0D` | `$F54B` | `$01` | `$03` | `$FF` | `$0280` | `$12`&rarr;`$0E`, `$12`&rarr;`$0E`, `$12`&rarr;`$0E`, `$12`&rarr;`$0E`, `$12`&rarr;`$0E` |
| `$0E` | `$F57D` | `$01` | `$03` | `$FF` | `$0280` | `$12`&rarr;`$00`, `$12`&rarr;`$00`, `$12`&rarr;`$00`, `$12`&rarr;`$00`, `$12`&rarr;`$00` |
| `$0F` | `$F5AF` | `$01` | `$02` | `$00` | `$0140` | `$14`&rarr;`$00`, `$13`&rarr;`$00`, `$13`&rarr;`$00` |
| `$10` | `$F5D4` | `$02` | `$07` | `$00` | `$0140` | `$22`&rarr;`$00`, `$21`&rarr;`$41`, `$23`&rarr;`$00` |
| `$11` | `$F5FC` | `$02` | `$08` | `$00` | `$0282` | `$25`&rarr;`$06`, `$24`&rarr;`$00`, `$24`&rarr;`$00`, `$24`&rarr;`$00`, `$26`&rarr;`$31` |
| `$12` | `$F62E` | `$03` | `$0B` | `$00` | `$00A0` | `$0F`&rarr;`$00`, `$10`&rarr;`$00` |
| `$13` | `$F651` | `$01` | `$10` | `$00` | `$013F` | `$01`&rarr;`$00`, `$0A`&rarr;`$00`, `$02`&rarr;`$00` |
| `$14` | `$F679` | `$03` | `$13` | `$00` | `$013F` | `$05`&rarr;`$00`, `$06`&rarr;`$00`, `$07`&rarr;`$00` |
| `$15` | `$F6A1` | `$03` | `$0B` | `$00` | `$00A0` | `$01`&rarr;`$00`, `$02`&rarr;`$00` |
| `$16` | `$F6C4` | `$01` | `$0C` | `$00` | `$0000` | `$09`&rarr;`$00` |
| `$17` | `$F6E2` | `$04` | `$05` | `$00` | `$013F` | `$27`&rarr;`$00`, `$26`&rarr;`$00`, `$25`&rarr;`$01` |
| `$18` | `$F707` | `$02` | `$0A` | `$00` | `$0282` | `$2A`&rarr;`$19`, `$2A`&rarr;`$19`, `$2C`&rarr;`$19`, `$2A`&rarr;`$19`, `$2A`&rarr;`$19` |
| `$19` | `$F739` | `$02` | `$0A` | `$00` | `$0282` | `$2A`&rarr;`$1A`, `$2A`&rarr;`$1A`, `$2A`&rarr;`$1A`, `$2A`&rarr;`$1A`, `$2A`&rarr;`$1A` |
| `$1A` | `$F76B` | `$02` | `$0A` | `$00` | `$0282` | `$2A`&rarr;`$1B`, `$28`&rarr;`$1B`, `$2A`&rarr;`$1B`, `$2A`&rarr;`$1B`, `$2A`&rarr;`$1B` |
| `$1B` | `$F79D` | `$02` | `$0A` | `$00` | `$0282` | `$2B`&rarr;`$18`, `$2A`&rarr;`$18`, `$2A`&rarr;`$18`, `$2A`&rarr;`$18`, `$2A`&rarr;`$18` |
| `$1C` | `$F7CF` | `$04` | `$15` | `$00` | `$01B0` | `$21`&rarr;`$00`, `$22`&rarr;`$00`, `$23`&rarr;`$00`, `$24`&rarr;`$00` |
| `$1D` | `$F7FB` | `$03` | `$14` | `$00` | `$009F` | `$03`&rarr;`$2B`, `$04`&rarr;`$00` |
| `$1E` | `$F81E` | `$03` | `$0C` | `$00` | `$0126` | `$08`&rarr;`$00`, `$09`&rarr;`$00`, `$0A`&rarr;`$00` |
| `$1F` | `$F846` | `$07` | `$16` | `$07` | `$0000` | `$10`&rarr;`$07` |
| `$20` | `$F864` | `$07` | `$0B` | `$07` | `$0000` | `$13`&rarr;`$25` |
| `$21` | `$F881` | `$07` | `$0C` | `$07` | `$0132` | `$08`&rarr;`$00`, `$01`&rarr;`$00`, `$09`&rarr;`$00` |
| `$22` | `$F8A9` | `$07` | `$0C` | `$07` | `$0132` | `$07`&rarr;`$21`, `$05`&rarr;`$1C`, `$06`&rarr;`$21` |
| `$23` | `$F8D1` | `$07` | `$0C` | `$07` | `$0132` | `$07`&rarr;`$22`, `$09`&rarr;`$00` |
| `$24` | `$F8F4` | `$07` | `$0B` | `$07` | `$0282` | `$08`&rarr;`$00`, `$06`&rarr;`$23`, `$07`&rarr;`$23`, `$01`&rarr;`$00`, `$06`&rarr;`$29` |
| `$25` | `$F926` | `$07` | `$0B` | `$07` | `$00A0` | `$07`&rarr;`$24`, `$06`&rarr;`$24` |
| `$26` | `$F949` | `$07` | `$0B` | `$07` | `$0132` | `$0B`&rarr;`$25`, `$14`&rarr;`$00`, `$0A`&rarr;`$24` |
| `$27` | `$F971` | `$07` | `$0D` | `$07` | `$01D2` | `$02`&rarr;`$2F`, `$08`&rarr;`$00`, `$04`&rarr;`$00`, `$09`&rarr;`$00` |
| `$28` | `$F99E` | `$07` | `$0D` | `$07` | `$0296` | `$02`&rarr;`$27`, `$07`&rarr;`$27`, `$06`&rarr;`$27` |
| `$29` | `$F9C6` | `$07` | `$0D` | `$07` | `$0132` | `$02`&rarr;`$28`, `$02`&rarr;`$28`, `$02`&rarr;`$28` |
| `$2A` | `$F9EE` | `$07` | `$0C` | `$07` | `$027E` | `$0B`&rarr;`$22`, `$01`&rarr;`$00`, `$05`&rarr;`$29`, `$05`&rarr;`$29`, `$09`&rarr;`$00` |
| `$2B` | `$FA20` | `$07` | `$0C` | `$07` | `$0132` | `$08`&rarr;`$00`, `$03`&rarr;`$2A`, `$09`&rarr;`$00` |
| `$2C` | `$FA48` | `$07` | `$0B` | `$07` | `$0000` | `$03`&rarr;`$24` |
| `$2D` | `$FA66` | `$07` | `$0C` | `$FF` | `$0280` | `$03`&rarr;`$2D`, `$03`&rarr;`$2D`, `$03`&rarr;`$2D`, `$03`&rarr;`$2D`, `$03`&rarr;`$2D` |
| `$2E` | `$FA98` | `$07` | `$0B` | `$07` | `$009F` | `$0D`&rarr;`$27`, `$0C`&rarr;`$00` |
| `$2F` | `$FAB9` | `$07` | `$16` | `$07` | `$0000` | `$0E`&rarr;`$1F` |
| `$30` | `$FAD7` | `$02` | `$0E` | `$00` | `$0000` | `$29`&rarr;`$00` |
| `$31` | `$FAF5` | `$02` | `$0E` | `$00` | `$0280` | `$30`&rarr;`$32`, `$30`&rarr;`$32`, `$2E`&rarr;`$32`, `$2D`&rarr;`$32`, `$30`&rarr;`$32` |
| `$32` | `$FB27` | `$02` | `$0E` | `$00` | `$0280` | `$32`&rarr;`$33`, `$2D`&rarr;`$33`, `$30`&rarr;`$33`, `$2D`&rarr;`$33`, `$33`&rarr;`$33` |
| `$33` | `$FB59` | `$02` | `$0E` | `$00` | `$0280` | `$29`&rarr;`$00`, `$29`&rarr;`$00`, `$29`&rarr;`$00`, `$2F`&rarr;`$35`, `$2F`&rarr;`$38` |
| `$34` | `$FB8B` | `$02` | `$0E` | `$00` | `$0000` | `$27`&rarr;`$1D` |
| `$35` | `$FBA9` | `$02` | `$0E` | `$00` | `$01C2` | `$30`&rarr;`$36`, `$30`&rarr;`$37`, `$31`&rarr;`$00`, `$30`&rarr;`$30` |
| `$36` | `$FBD6` | `$01` | `$0E` | `$00` | `$0000` | `$09`&rarr;`$00` |
| `$37` | `$FBF4` | `$02` | `$0E` | `$00` | `$0000` | `$29`&rarr;`$00` |
| `$38` | `$FC12` | `$02` | `$0E` | `$FF` | `$0000` | `$2F`&rarr;`$39` |
| `$39` | `$FC30` | `$01` | `$03` | `$FF` | `$0000` | `$10`&rarr;`$3A` |
| `$3A` | `$FC4E` | `$01` | `$03` | `$FF` | `$0000` | `$0F`&rarr;`$3B` |
| `$3B` | `$FC6C` | `$01` | `$03` | `$FF` | `$0000` | `$11`&rarr;`$3C` |
| `$3C` | `$FC8A` | `$01` | `$03` | `$FF` | `$0000` | `$0E`&rarr;`$00` |
| `$40` | `$FCA8` | `$08` | `$0C` | `$00` | `$0000` | `$31`&rarr;`$44` |
| `$41` | `$FCC6` | `$08` | `$12` | `$00` | `$0140` | `$2B`&rarr;`$00`, `$2C`&rarr;`$44`, `$32`&rarr;`$00` |
| `$42` | `$FCEE` | `$08` | `$12` | `$00` | `$009F` | `$29`&rarr;`$43`, `$2A`&rarr;`$00` |
| `$43` | `$FD11` | `$08` | `$0C` | `$00` | `$0000` | `$30`&rarr;`$00` |
| `$44` | `$FD2F` | `$08` | `$12` | `$00` | `$0140` | `$2E`&rarr;`$45`, `$2D`&rarr;`$4F`, `$2F`&rarr;`$00` |
| `$45` | `$FD57` | `$08` | `$12` | `$00` | `$0000` | `$21`&rarr;`$46` |
| `$46` | `$FD75` | `$08` | `$12` | `$00` | `$0000` | `$21`&rarr;`$47` |
| `$47` | `$FD93` | `$08` | `$12` | `$00` | `$0280` | `$23`&rarr;`$4B`, `$24`&rarr;`$4C`, `$25`&rarr;`$00`, `$24`&rarr;`$4D`, `$24`&rarr;`$4E` |
| `$48` | `$FDC5` | `$08` | `$12` | `$00` | `$0000` | `$26`&rarr;`$47` |
| `$49` | `$FDE3` | `$08` | `$11` | `$00` | `$0000` | `$22`&rarr;`$00` |
| `$4A` | `$FE01` | `$08` | `$11` | `$00` | `$0000` | `$22`&rarr;`$00` |
| `$4B` | `$FE1F` | `$08` | `$12` | `$00` | `$0000` | `$27`&rarr;`$00` |
| `$4C` | `$FE3D` | `$08` | `$12` | `$00` | `$0000` | `$27`&rarr;`$00` |
| `$4D` | `$FE5B` | `$08` | `$11` | `$00` | `$0000` | `$28`&rarr;`$00` |
| `$4E` | `$FE79` | `$08` | `$12` | `$00` | `$0000` | `$27`&rarr;`$00` |
| `$4F` | `$FE97` | `$08` | `$12` | `$00` | `$0000` | `$33`&rarr;`$00` |

## Exit detail

The listing below predates the correct parse and shows only the **north** table:
its `screen` column is the north arrival index and its `cross` column is in fact
the **south destination**, not a coordinate. See "A room has four kinds of exit"
above for the five arrays as they actually are; `tools/areas.py` reports
`north`, `north_scr`, `south`, `south_scr`, `west` and `east`.

Several entries share one event id and differ only in the segment you trigger it
from -- the index is `(world_position - $18) / 160`, computed by `sub_D190`.

**`$01`** &nbsp; id `$03` &rarr; `$0B` @ scr `$03`, cross `$04` &nbsp; id `$04` &rarr; `$09` @ scr `$05`, cross `$00` &nbsp; id `$05` &rarr; `$00` @ scr `$00`, cross `$17`  
**`$02`** &nbsp; id `$06` &rarr; `$13` @ scr `$03`, cross `$03`  
**`$03`** &nbsp; id `$13` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$13` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$07` &rarr; `$02` @ scr `$05`, cross `$00`  
**`$04`** &nbsp; id `$08` &rarr; `$01` @ scr `$05`, cross `$05`  
**`$05`** &nbsp; id `$08` &rarr; `$04` @ scr `$04`, cross `$06`  
**`$06`** &nbsp; id `$08` &rarr; `$05` @ scr `$04`, cross `$11`  
**`$07`** &nbsp; id `$0F` &rarr; `$92` @ scr `$01`, cross `$1F`  
**`$08`** &nbsp; id `$0C` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$0D` &rarr; `$13` @ scr `$1E`, cross `$00`  
**`$09`** &nbsp; id `$2F` &rarr; `$0A` @ scr `$05`, cross `$01`  
**`$0A`** &nbsp; id `$2F` &rarr; `$18` @ scr `$2F`, cross `$09`  
**`$0B`** &nbsp; id `$08` &rarr; `$0C` @ scr `$03`, cross `$01`  
**`$0C`** &nbsp; id `$0B` &rarr; `$10` @ scr `$19`, cross `$0B`  
**`$0D`** &nbsp; id `$12` &rarr; `$0E` @ scr `$05`, cross `$00` &nbsp; id `$12` &rarr; `$0E` @ scr `$19`, cross `$00` &nbsp; id `$12` &rarr; `$0E` @ scr `$2D`, cross `$00` &nbsp; id `$12` &rarr; `$0E` @ scr `$41`, cross `$00` &nbsp; id `$12` &rarr; `$0E` @ scr `$55`, cross `$00`  
**`$0E`** &nbsp; id `$12` &rarr; `$00` @ scr `$00`, cross `$0D` &nbsp; id `$12` &rarr; `$00` @ scr `$05`, cross `$0D` &nbsp; id `$12` &rarr; `$00` @ scr `$19`, cross `$0D` &nbsp; id `$12` &rarr; `$00` @ scr `$00`, cross `$0D` &nbsp; id `$12` &rarr; `$00` @ scr `$05`, cross `$0D`  
**`$0F`** &nbsp; id `$14` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$13` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$13` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$10`** &nbsp; id `$22` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$21` &rarr; `$41` @ scr `$19`, cross `$0C` &nbsp; id `$23` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$11`** &nbsp; id `$25` &rarr; `$06` @ scr `$04`, cross `$00` &nbsp; id `$24` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$24` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$24` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$26` &rarr; `$31` @ scr `$40`, cross `$00`  
**`$12`** &nbsp; id `$0F` &rarr; `$00` @ scr `$00`, cross `$87` &nbsp; id `$10` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$13`** &nbsp; id `$01` &rarr; `$00` @ scr `$00`, cross `$02` &nbsp; id `$0A` &rarr; `$00` @ scr `$00`, cross `$08` &nbsp; id `$02` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$14`** &nbsp; id `$05` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$06` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$07` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$15`** &nbsp; id `$01` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$02` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$16`** &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$93`  
**`$17`** &nbsp; id `$27` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$26` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$25` &rarr; `$01` @ scr `$2A`, cross `$00`  
**`$18`** &nbsp; id `$2A` &rarr; `$19` @ scr `$0A`, cross `$1A` &nbsp; id `$2A` &rarr; `$19` @ scr `$1E`, cross `$1A` &nbsp; id `$2C` &rarr; `$19` @ scr `$32`, cross `$0A` &nbsp; id `$2A` &rarr; `$19` @ scr `$46`, cross `$1A` &nbsp; id `$2A` &rarr; `$19` @ scr `$5A`, cross `$1A`  
**`$19`** &nbsp; id `$2A` &rarr; `$1A` @ scr `$0A`, cross `$18` &nbsp; id `$2A` &rarr; `$1A` @ scr `$1E`, cross `$18` &nbsp; id `$2A` &rarr; `$1A` @ scr `$32`, cross `$18` &nbsp; id `$2A` &rarr; `$1A` @ scr `$46`, cross `$18` &nbsp; id `$2A` &rarr; `$1A` @ scr `$5A`, cross `$18`  
**`$1A`** &nbsp; id `$2A` &rarr; `$1B` @ scr `$0A`, cross `$19` &nbsp; id `$28` &rarr; `$1B` @ scr `$1E`, cross `$19` &nbsp; id `$2A` &rarr; `$1B` @ scr `$32`, cross `$19` &nbsp; id `$2A` &rarr; `$1B` @ scr `$46`, cross `$19` &nbsp; id `$2A` &rarr; `$1B` @ scr `$5A`, cross `$19`  
**`$1B`** &nbsp; id `$2B` &rarr; `$18` @ scr `$0A`, cross `$1A` &nbsp; id `$2A` &rarr; `$18` @ scr `$1E`, cross `$1A` &nbsp; id `$2A` &rarr; `$18` @ scr `$32`, cross `$1A` &nbsp; id `$2A` &rarr; `$18` @ scr `$46`, cross `$1A` &nbsp; id `$2A` &rarr; `$18` @ scr `$5A`, cross `$1A`  
**`$1C`** &nbsp; id `$21` &rarr; `$00` @ scr `$00`, cross `$22` &nbsp; id `$22` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$23` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$24` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$1D`** &nbsp; id `$03` &rarr; `$2B` @ scr `$05`, cross `$B4` &nbsp; id `$04` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$1E`** &nbsp; id `$08` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$0A` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$1F`** &nbsp; id `$10` &rarr; `$07` @ scr `$04`, cross `$2F`  
**`$20`** &nbsp; id `$13` &rarr; `$25` @ scr `$05`, cross `$00`  
**`$21`** &nbsp; id `$08` &rarr; `$00` @ scr `$00`, cross `$22` &nbsp; id `$01` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$22`  
**`$22`** &nbsp; id `$07` &rarr; `$21` @ scr `$05`, cross `$23` &nbsp; id `$05` &rarr; `$1C` @ scr `$02`, cross `$00` &nbsp; id `$06` &rarr; `$21` @ scr `$2D`, cross `$2A`  
**`$23`** &nbsp; id `$07` &rarr; `$22` @ scr `$05`, cross `$24` &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$24`  
**`$24`** &nbsp; id `$08` &rarr; `$00` @ scr `$00`, cross `$2C` &nbsp; id `$06` &rarr; `$23` @ scr `$05`, cross `$25` &nbsp; id `$07` &rarr; `$23` @ scr `$19`, cross `$25` &nbsp; id `$01` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$06` &rarr; `$29` @ scr `$05`, cross `$26`  
**`$25`** &nbsp; id `$07` &rarr; `$24` @ scr `$19`, cross `$20` &nbsp; id `$06` &rarr; `$24` @ scr `$2D`, cross `$26`  
**`$26`** &nbsp; id `$0B` &rarr; `$25` @ scr `$19`, cross `$00` &nbsp; id `$14` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$0A` &rarr; `$24` @ scr `$55`, cross `$00`  
**`$27`** &nbsp; id `$02` &rarr; `$2F` @ scr `$05`, cross `$28` &nbsp; id `$08` &rarr; `$00` @ scr `$00`, cross `$28` &nbsp; id `$04` &rarr; `$00` @ scr `$00`, cross `$28` &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$2E`  
**`$28`** &nbsp; id `$02` &rarr; `$27` @ scr `$05`, cross `$29` &nbsp; id `$07` &rarr; `$27` @ scr `$19`, cross `$29` &nbsp; id `$06` &rarr; `$27` @ scr `$2D`, cross `$29`  
**`$29`** &nbsp; id `$02` &rarr; `$28` @ scr `$05`, cross `$24` &nbsp; id `$02` &rarr; `$28` @ scr `$19`, cross `$2A` &nbsp; id `$02` &rarr; `$28` @ scr `$2D`, cross `$2A`  
**`$2A`** &nbsp; id `$0B` &rarr; `$22` @ scr `$2D`, cross `$00` &nbsp; id `$01` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$05` &rarr; `$29` @ scr `$19`, cross `$00` &nbsp; id `$05` &rarr; `$29` @ scr `$2D`, cross `$00` &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$2B`  
**`$2B`** &nbsp; id `$08` &rarr; `$00` @ scr `$05`, cross `$9D` &nbsp; id `$03` &rarr; `$2A` @ scr `$55`, cross `$2D` &nbsp; id `$09` &rarr; `$00` @ scr `$23`, cross `$11`  
**`$2C`** &nbsp; id `$03` &rarr; `$24` @ scr `$05`, cross `$2C`  
**`$2D`** &nbsp; id `$03` &rarr; `$2D` @ scr `$19`, cross `$2D` &nbsp; id `$03` &rarr; `$2D` @ scr `$2D`, cross `$2D` &nbsp; id `$03` &rarr; `$2D` @ scr `$41`, cross `$2D` &nbsp; id `$03` &rarr; `$2D` @ scr `$55`, cross `$2B` &nbsp; id `$03` &rarr; `$2D` @ scr `$05`, cross `$2D`  
**`$2E`** &nbsp; id `$0D` &rarr; `$27` @ scr `$41`, cross `$00` &nbsp; id `$0C` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$2F`** &nbsp; id `$0E` &rarr; `$1F` @ scr `$04`, cross `$27`  
**`$30`** &nbsp; id `$29` &rarr; `$00` @ scr `$00`, cross `$35`  
**`$31`** &nbsp; id `$30` &rarr; `$32` @ scr `$04`, cross `$00` &nbsp; id `$30` &rarr; `$32` @ scr `$18`, cross `$00` &nbsp; id `$2E` &rarr; `$32` @ scr `$2C`, cross `$00` &nbsp; id `$2D` &rarr; `$32` @ scr `$40`, cross `$11` &nbsp; id `$30` &rarr; `$32` @ scr `$54`, cross `$00`  
**`$32`** &nbsp; id `$32` &rarr; `$33` @ scr `$09`, cross `$31` &nbsp; id `$2D` &rarr; `$33` @ scr `$1D`, cross `$31` &nbsp; id `$30` &rarr; `$33` @ scr `$31`, cross `$00` &nbsp; id `$2D` &rarr; `$33` @ scr `$40`, cross `$31` &nbsp; id `$33` &rarr; `$33` @ scr `$54`, cross `$31`  
**`$33`** &nbsp; id `$29` &rarr; `$00` @ scr `$00`, cross `$32` &nbsp; id `$29` &rarr; `$00` @ scr `$00`, cross `$32` &nbsp; id `$29` &rarr; `$00` @ scr `$00`, cross `$32` &nbsp; id `$2F` &rarr; `$35` @ scr `$2C`, cross `$32` &nbsp; id `$2F` &rarr; `$38` @ scr `$04`, cross `$32`  
**`$34`** &nbsp; id `$27` &rarr; `$1D` @ scr `$07`, cross `$00`  
**`$35`** &nbsp; id `$30` &rarr; `$36` @ scr `$07`, cross `$00` &nbsp; id `$30` &rarr; `$37` @ scr `$09`, cross `$00` &nbsp; id `$31` &rarr; `$00` @ scr `$00`, cross `$33` &nbsp; id `$30` &rarr; `$30` @ scr `$09`, cross `$00`  
**`$36`** &nbsp; id `$09` &rarr; `$00` @ scr `$00`, cross `$35`  
**`$37`** &nbsp; id `$29` &rarr; `$00` @ scr `$00`, cross `$35`  
**`$38`** &nbsp; id `$2F` &rarr; `$39` @ scr `$06`, cross `$33`  
**`$39`** &nbsp; id `$10` &rarr; `$3A` @ scr `$05`, cross `$38`  
**`$3A`** &nbsp; id `$0F` &rarr; `$3B` @ scr `$08`, cross `$39`  
**`$3B`** &nbsp; id `$11` &rarr; `$3C` @ scr `$05`, cross `$3A`  
**`$3C`** &nbsp; id `$0E` &rarr; `$00` @ scr `$00`, cross `$3A`  
**`$40`** &nbsp; id `$31` &rarr; `$44` @ scr `$32`, cross `$00`  
**`$41`** &nbsp; id `$2B` &rarr; `$00` @ scr `$00`, cross `$00` &nbsp; id `$2C` &rarr; `$44` @ scr `$19`, cross `$90` &nbsp; id `$32` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$42`** &nbsp; id `$29` &rarr; `$43` @ scr `$00`, cross `$00` &nbsp; id `$2A` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$43`** &nbsp; id `$30` &rarr; `$00` @ scr `$00`, cross `$42`  
**`$44`** &nbsp; id `$2E` &rarr; `$45` @ scr `$03`, cross `$00` &nbsp; id `$2D` &rarr; `$4F` @ scr `$06`, cross `$41` &nbsp; id `$2F` &rarr; `$00` @ scr `$00`, cross `$40`  
**`$45`** &nbsp; id `$21` &rarr; `$46` @ scr `$03`, cross `$44`  
**`$46`** &nbsp; id `$21` &rarr; `$47` @ scr `$34`, cross `$45`  
**`$47`** &nbsp; id `$23` &rarr; `$4B` @ scr `$05`, cross `$48` &nbsp; id `$24` &rarr; `$4C` @ scr `$05`, cross `$00` &nbsp; id `$25` &rarr; `$00` @ scr `$00`, cross `$46` &nbsp; id `$24` &rarr; `$4D` @ scr `$05`, cross `$00` &nbsp; id `$24` &rarr; `$4E` @ scr `$05`, cross `$00`  
**`$48`** &nbsp; id `$26` &rarr; `$47` @ scr `$01`, cross `$00`  
**`$49`** &nbsp; id `$22` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$4A`** &nbsp; id `$22` &rarr; `$00` @ scr `$00`, cross `$00`  
**`$4B`** &nbsp; id `$27` &rarr; `$00` @ scr `$00`, cross `$C7`  
**`$4C`** &nbsp; id `$27` &rarr; `$00` @ scr `$00`, cross `$C7`  
**`$4D`** &nbsp; id `$28` &rarr; `$00` @ scr `$00`, cross `$C7`  
**`$4E`** &nbsp; id `$27` &rarr; `$00` @ scr `$00`, cross `$C7`  
**`$4F`** &nbsp; id `$33` &rarr; `$00` @ scr `$00`, cross `$44`

## A room has four kinds of exit, from three places

North and south are per scroll segment; east and west are one destination for
the whole room. All four live in the area header.

| edge | header | read at | how it is taken |
|---|---|---|---|
| north | array 2 (dest) + 3 (arrival) | `f6:$57E2`, `$58A5` | `player_pos_cross` drops below `$0A` |
| south | array 4 (dest) + 5 (arrival) | `f6:$57F9`, `$58D6` | `player_pos_cross` reaches `$A0` |
| **west** | **+5** (`$1F20`) | `f6:$591E` | world position falls below `$1D` |
| **east** | **+6** (`$1F21`) | `f6:$5935` | world position reaches `map_limit` |

The two vertical tables are told apart by where they drop the player: the north
table sets `player_pos_cross` to `$9E`, the bottom of the arriving room, and the
south table sets `$0C`, the top. A destination of `$00` means that edge is a
wall -- and for the east edge, that is exactly when the `map_limit` clamp at
`f6:$53A6` bites instead.

Note that there are **five** arrays, not four: north destination, north arrival,
south destination, south arrival, and the slice list they are all indexed
alongside. Reading four of them and treating the last as a coordinate loses half
the vertical connectivity.

### East and west are where the caves and woods connect

20 rooms have a west exit and 23 an east exit, 43 in all, and they cluster:

* the cave run `$1F`-`$2F`
* the woods `$30`-`$38`
* `$1C` east to `$40`, which is the basement dropping into the caves
* `$4A` east to `$47`, the only way out of the crypt-key room, which has no
  scroll exits at all

**The loop traps are self-referencing side exits.** `$2C`, `$2D`, `$31` and
`$38` each name themselves as both their east and west destination, so walking
either way returns you to the same room. Nothing else in the exit data does
this.

## Bit 2 marks water, and the engine never reads it

`CheckTerrainUnderPlayer` (`f6:$55E3`) tests the terrain byte with **`AND #$03`
and nothing else**, so `$05`, `$06` and `$07` block exactly as `$01`, `$02` and
`$03` do. Bit 2 is an authoring marker rather than a rule.

What it marks is water, and it is rare:

| value | class | rooms |
|---|---|---|
| `$05` | 1 | `$01` |
| `$06` | 2 | `$01 $0F` |
| `$07` | 3 | `$01 $02 $03 $07 $0F $11` |

In room `$01` those three are the fountain, which is the one place the necklace
lets the player cross water.

**The necklace does not read the terrain either.** `f7:$D0C0` is a position
test, not a property test:

    sel_item == $03            the necklace, selected rather than carried
    screen_kind_idx == $01     room $01 only
    world position inside a fixed rectangle
      -> ram_1FA9 = $FF

and `f6:$5666` reads that flag at the point where blocking terrain would stop
the player, letting them through regardless of what the terrain says.

So the crossing is a hardcoded rectangle in one room. The same `$07` water in
`$02`, `$03`, `$07`, `$0F` and `$11` is simply impassable -- the necklace does
nothing there, because the room check fails before the rectangle is considered.

The two blocking classes are the two sides of a diagonal through the cell.
`cell_half` is 1 when `2*x + y` within the cell reaches `$10` and 2 below it,
and a class blocks when it equals `cell_half` -- so **class 1 blocks the lower
right half and class 2 the upper left**.

`tools/editor.py` can make bit 2 mean what it looks like it means: a shim at
the blocking decision lets the player through any water square while the
necklace is selected, in every room. See `EDITOR.md`.

## Doors are terrain, and the boss doors are gated

Terrain with bit 7 set is a scripted square rather than ground. The code comes
from the area's property table, indexed by `(cell >> 1) & $7F`, so two adjacent
characters share one terrain property.

| code | what | where |
|---|---|---|
| `$8C` | door taking the **west** destination | `$14 $41 $47 $48` |
| `$8F` | door taking the **north** table | `$07 $10 $1D $2F $34 $47` |
| `$81` | door to `$2B` | `$11` |
| `$82` | door to `$14`, needs a weapon | `$01` |
| `$83` | door to `$15`, sets a forced message | `$08` |
| `$84` | door to `$16`, needs `weapon_level > 0` | `$13` |
| `$85` | door to `$1E`, **needs the crypt key selected** | `$17` |
| `$86` | door to `$1C`, needs the Ram beaten, nothing selected, `weapon_level > 0` | `$40` |
| `$90` | paired door: `$16` and `$36` lead to each other | `$16 $36` |
| `$A0` | the healing well | `$34` |
| `$A1` | hurting ground -- an area, not a point | `$1C`, 31 cells |
| `$EF` | **the win** | `$1A` |
| `$F1` | **boss door: Skull** | `$1E` |
| `$F2` | **boss door: Ram** | `$15` |
| `$F3` | **boss door: Dr Evil** | `$3C` |

`f6:$5810` turns a `$F0`-and-up square into a boss entry by writing it to `$89`,
which `f6:$4CCA` later turns into `mode_flag = code - $F0`. Each is gated on a
different `boss_flags` bit, so a door stops working once its boss is beaten:

| door | boss | gate |
|---|---|---|
| `$F1` | 1, Skull | `boss_flags & $02` |
| `$F2` | 2, Ram | `boss_flags & $01` |
| `$F3` | 3, Dr Evil | `boss_flags & $04` |

That numbering agrees with the setup records: boss 3 is the one whose hitbox
alternates between two ears, which is Dr Evil.

A scan that walks the 1000-byte grid as one flat run instead of ten bands of a
hundred misses most of these -- it finds the Ram's door and concludes the other
two are placed at run time. They are not; all three are ordinary terrain.

## The scripted doors carry their own gates

`HandlePendingTerrain` (`f6:$567E`) dispatches the `$8x` codes one by one, and
each ends in `sub_5789`, which takes the destination in `A`, the arrival screen
index in `X` and the arrival cross position in `Y`. Several test something first
and, when the test fails, call `sub_687E` with a refusal glyph (`$38` or `$39`)
instead of moving the player -- the door is drawn as shut rather than being
absent.

The gates are the interesting part, because they encode progression directly in
terrain rather than in a quest flag:

* `$85`, the way into the crypt, requires `sel_item == 2` -- the **crypt key
  actually held in hand**, not merely owned.
* `$86`, into `$1C`, wants three things at once: `boss_flags` bit 0 (the Ram
  already beaten), **no** item selected, and `weapon_level > 0`.
* `$84` and `$86` both refuse a `weapon_level` of 0, so the knife alone will not
  open them.

`$90` is the only symmetric pair: the handler compares `screen_kind_idx` against
`$36` and sends the player to `$16` if it matches, `$36` otherwise, so one code
serves both ends of the same doorway.

## What an area bank contains

Each of banks 1-4 serves two areas and is almost entirely claimed by two
readers:

* **`$8000`-`$8FFF` and `$A000`-`$AFFF`** -- two character sets, 128 two-byte
  characters each, selected by `tbl_AreaPage` as CHARBASE `$80` or `$A0`;
* **39 terrain slices** of 200 bytes, 10 bands of 20, at the pointers in
  `tbl_F2B4` / `tbl_F2E8`.

That is 15992 of the window's 16384 bytes. The remaining 296 sit at `$BED8`,
which is slice selector `$34` -- all zeroes, an empty slice. Selectors `$3C`,
`$3D`, `$3E`, `$50` and `$52` exist in the table but their pointers land inside
the character sets, so they are dead slots rather than terrain.

No room references a selector above `$33`.
