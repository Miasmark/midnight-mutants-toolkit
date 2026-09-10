# Midnight Mutants -- repair and tweak pack

Two BPS patches, one per region. They carry the same set of changes; the only
difference is that the PAL build also corrects the music tempo, which the
European release never had.

| | NTSC | PAL |
|---|---|---|
| patch | `mm-pack-ntsc.bps` | `mm-pack-pal.bps` |
| bytes changed | 219 | 237 |
| patch size | 440 B | 462 B |
| base ROM CRC32 | `187EC84E` | `7CA6D521` |

**Patches are built against the cartridge data only**, with the 128-byte `.a78`
header excluded, so either patch applies to any dump of its region regardless of
which header the file carries. A patch still only fits its own region -- NTSC and
PAL differ in 16,467 bytes, so each refuses the other. Verified both ways:

```
mm-pack-ntsc.bps   applies to (NTSC) and (NTSC)(trebor),  refuses (Europe)
mm-pack-pal.bps    applies to (Europe) and (PAL)(Trebor), refuses (NTSC)
```

---

## The pack also ships as a bundle you can pick from

`mm-ntsc.abp` and `mm-pal.abp` carry the same edits as one option per
change -- twelve for NTSC, thirteen for PAL -- so the table below can be
taken a row at a time instead of whole:

```
python tools/patchset.py list  patches/mm-ntsc.abp
python tools/patchset.py apply patches/mm-ntsc.abp     --rom "Midnight Mutants (NTSC) (Atari) (1990).a78"     --with icon-fixes,reticle-leg,mega-frames --out fixed.a78
```

Each option names the byte ranges it edits and carries a CRC32 of what it
expects to find there, so applying checks a few bytes rather than the
whole file, a dump with a different header still passes, and a cartridge
that already has some of these keeps them. Built by `build-bundle.py`.

Three of the pack's edits are settings rather than switches and are not in
the bundle: the purity-necklace gate with its contact rule, the zombie
toughness value and the library item placement. They want an option each,
written by someone who knows the intent.

## The signature, which the BPS patches get wrong

**A patched cartridge built from `mm-pack-ntsc.bps` will not run on a real
NTSC 7800.** The console hashes the cartridge and checks a signature at
`$FF80`-`$FFF7`; when it does not match, it does not refuse -- it starts up
in **2600 mode**, which looks like a black screen rather than an error.
PAL consoles do not check and no emulator verifies it, so this only shows
up on hardware.

Only the last 4K is hashed here (`$FFF9` is `$F7`), so most of the pack is
outside the window. **Exactly three of its 219 changed bytes are inside**
-- `$1FE9E`, `$1FEAD`, `$1FEAE` -- and all three come from one edit, the
library item placement. Every other repair and change in this pack leaves
the signature intact.

`tools/sign7800.py` verifies and repairs it, and costs 120 bytes at the
end of the image:

```
python tools/sign7800.py --write fixed.bin
```

The `.abp` route does this for you: `patchset.py` signs what it writes and
says so. The two `.bps` files do not, and cannot -- a BPS is a fixed delta,
and the correct signature depends on which options you chose.

---

## Repairs

Things the stock cartridge gets wrong.

| | cost |
|---|---|
| **Debug cheat** -- PAUSE plus four button presses was meant to refill purity and grant health. Two of the four counter states branched into data, and so did both wrong-button exits; since the IRQ vector is the reset entry, each was a soft reboot. Four branch operands. | in place |
| **Selected-item icons** -- the crypt key was invisible and the necklace a smudge, both drawn on a palette whose first colour is pure black; the plasmic pumpkin showed the *heart's* icon. | 4 bytes |
| **Reticle leg** -- the last frame of a special actor's death drew the Grampa screen's targeting bracket as the corpse's right leg. | 1 byte |
| **Death frame overruns** -- two animations index a countdown into a table one entry shorter than the seed allows, so the first frame of each reads the `$A5` opcode of the following routine and draws garbage. Affects crows, bats, ground enemies and spiders (`dat_5CE6`), and ghosts (`dat_6219`). | 1 byte each |
| **Four pickups that never shimmer** -- a message's terminator decides whether the banner pulses, `$FE` for yes and `$FF` for no. The cross and the three weapons above the knife end `$FF`; every other pickup in the game ends `$FE`, including the knife's own four lines. | 4 bytes |
| **Mega blaster's lost frames** -- it asks for four phases but its run repeats two. Cells `$A8`/`$AA` hold two more frames of the same orb that nothing referenced. | 2 bytes |
| **PAL music tempo** *(PAL only)* -- durations are frame counts and the European release was never retimed, so everything played at 83.3% speed. An extra tick every fifth frame, from a shim in free space. | 16 bytes |

## Changes

Things the stock cartridge does deliberately, changed on purpose.

| | |
|---|---|
| **Halve-health now needs the necklace** | The gate that halves every source of health damage read `itm_cross`; it now reads `itm_necklace`. NTSC `f7:$D403`, PAL `f7:$D40C`. |
| **Special-actor contact halved** | 16 health to **8**, and it goes with the row above rather than standing alone. Moving the halve-health gate to the necklace is what the manual describes, and the manual is also why the necklace has to be worth wearing; 16 was four times the worst an ordinary enemy does, which is what made the caves punishing. |
| **Zombie kind 10 can be killed** | Its toughness seed was `$00`, which overflows instantly and made it inert. Now `$F4` -- 12 axe hits, 6 blaster, 4 mega. |
| **A diamond in the library** | Room `$4F`, on the floor in the gap between the two bookshelves. Diamonds raise the health ceiling, and two of them are the price of being revived. |
| **Water walk by terrain** | The necklace crossing was a position test locked to room `$01`. It now reads bit 2 of the terrain, which marks water and which the engine never otherwise tests. |
| **The pumpkin's pickup line** | Kind 5 was the only item that granted in silence. It now says `TAKE IT TO THE PUMPKIN FIELDS / AND SET ME FREE!`, shimmering like every other pickup -- which, after the row above, they now all do. |
| **The axe turns over** | It was the only weapon with one animation frame, so it slid rather than tumbled. Now four distinct poses -- the fourth is `$CE` mirrored into `$88`, six bytes of page `$E0` that nothing referenced. The step gate also moves to the slower counter, which calms the knife and both blasters too. |

---

## Space

Both fit with room to spare. The display-flip compaction is enabled, which frees
a 28-byte pocket and keeps the tail whole.

| | free run left | of |
|---|---|---|
| NTSC | 48 bytes | 111 |
| PAL | 29 bytes | 108 |

Install order decides those numbers. The 28-byte pocket freed by the display-flip
compaction fits exactly one shim, and water walk is the one that leaves the tail's
free run longest -- on PAL, taking it second costs nine bytes and taking it third
does not fit at all. `build-pack.py` beside this file builds both regions in the
order that fits.

The PAL build is tighter because it also carries the 16-byte music shim.

## Applying

**Read this bit.** Because the patch covers the cartridge data and not the
header, it expects a **131,072-byte** ROM -- not the 131,200-byte `.a78`.

* **In the editor**, use **Load .bps**. It splits the header off for you and
  writes it back, so point it at the `.a78` and it just works.
* **In an external tool** -- Floating IPS, RomPatcher.js, beat -- give it a
  headerless dump. Feeding it the `.a78` fails with *"expects a 131072-byte ROM
  and yours is 131200"*. Strip the first 128 bytes, patch, then put them back:

  ```
  tail -c +129 "Midnight Mutants (NTSC) (Atari) (1990).a78" > mm.bin
  flips --apply mm-pack-ntsc.bps mm.bin mm-patched.bin
  head -c 128 "Midnight Mutants (NTSC) (Atari) (1990).a78" > out.a78
  cat mm-patched.bin >> out.a78
  ```

That is the cost of one patch covering every header variant; the alternative is
a separate patch per dump. The format verifies a CRC32 of the source, the target
and itself, so a wrong base ROM is refused rather than silently mangled.

## Notes

* `build-pack.py` rebuilds both regions from the stock dumps and is the
  authoritative list of what goes in.
* All 76 area headers still parse after patching, and the stock images round-trip
  byte-identically through the editor.
* The axe's fourth pose only shows because the tumble is on; without it the
  animation phase never advances.
* Kind 10 appears in rooms `$46` and `$4F` -- the same library the diamond is
  now in, so that room gains both a reward and something that can finally be
  killed for it. **Kind 11 is left alone**: it is also inert, but no room casts
  it, so giving it a seed would change nothing.
