# Midnight Mutants -- coverage

What this disassembly has looked at, measured rather than recalled.

## Code identified, by bank

`src/b7.asm` is bank 7 re-assembled at `$8000` for when it is paged into the
window, so it double-counts and is excluded here.

| bank | code bytes | of 16384 | holds |
|---|---|---|---|
| f6 | 8888 | **54.2%** | main loop, actors, terrain, items, transitions |
| b5 | 2101 | 12.8% | boss fights, the boss music |
| f7 | 1582 | 9.7% | sprites, area headers, service table, RESET |
| b0 | 1227 | 7.5% | sound engine, text renderer, the script |
| b3 | 668 | 4.1% | screen streams, the intro, the palette block |
| b1 | 0 | 0% | two character sets, terrain slices |
| b2 | 0 | 0% | two character sets, terrain slices |
| b4 | 0 | 0% | two character sets, terrain slices |
| **total** | **14466** | **11.0%** | |

The remaining 89% is data. For the largest part of it that is a measured
statement rather than an assumption: an area bank's `$8000`-`$BFFF` window is
**98% claimed** by two known readers -- the two character sets and the 39 terrain
slices -- with an all-zero slice accounting for most of the rest. See "What an
area bank contains" in `AREAS.md`.

For banks 0, 3, 5 and 7, whose data is interleaved with code, "data" means only
that the recursive descent never reached it.

## What is established

Traced to instructions, and where a claim is about behaviour, checked against a
running machine or against play:

* boot, banking, the display list chain, double buffering
* the world map: all 76 rooms, four kinds of exit, terrain generation, darkness
* doors: the scripted terrain squares, their destinations and their gates
* items: every inventory slot audited across all eight banks, and what reads it
* actors: spawning, toughness, the damage rules, the eight cross effects
* the roaming cast: which budget slot places each creature, and at what rate
* sprites: storage, assembly, animation, palettes and the composite-record table
* the player: movement, collision, firing, health, blood purity, both endings
* the bosses: setup records, per-boss routines, weak points, the difficulty ramp
* sound: the effect interpreter and the two-voice music engine, all 11 songs
* the script: 113 text records and their selection
* progression: `boss_flags`, boss doors, the win condition

## Rendered from the cartridge

Every image in the published pages is generated from ROM data rather than
captured from an emulator:

| | |
|---|---|
| `build/rooms/` | all 76 rooms, in colour, with items placed |
| `build/arenas/` | the three boss portraits |
| `build/maps/` | one terrain map per room |
| `build/gfx/` | character sets and sprite sheets |
| `build/music/` | every song as a WAV, plus each instrument playing its own notes |
| `build/palette_chart.png` | all 256 colour bytes |

## Where the spare bytes are

`tools/slack.py` reads the listings and reports code that could be encoded
smaller, sorted by whether shrinking it would disturb timing.

Two things the original does **not** waste, which bounds the exercise:

* **Absolute addressing of zero-page addresses: none.** Every one of the 6,773
  instructions that could have used the shorter form does. There is no free byte
  in that dimension anywhere in the cartridge.
* **Unreachable code: none.** Every label in every bank has a recorded caller,
  so no subroutine is dead weight.

What is left, in code that is not timing-critical:

| | sites | bytes |
|---|---|---|
| `JSR x` immediately followed by `RTS` | 18 | 18 |
| `JMP` onto an address holding only `RTS` | 18 | 36 |
| `LDA #v` where A already holds v | 14 | 28 |
| runs repeated verbatim, worth a subroutine | 63 | ~410 |

The first three are mechanical and total **82 bytes -- but in 37 pockets, 35 of
which are two or three bytes** and useful for nothing. The exception is
`sub_44EC`, the display double-buffer flip: it writes ten display-list high
bytes as ten `LDA #`/`STA` pairs where the value changes three times, twice
over. Compacting both halves yields a **single pocket of about 26 bytes**, and
compaction only makes the routine faster, which a bulk RAM write outside the
beam-critical path can afford.

The repeated-run total is larger but is a refactor, not an edit: each site pays
a `JSR`, and three of the candidates sit in the DLI chain where an extra stack
level and call overhead are not free.

### The 28-byte pocket works

`sub_44EC` -- the display double-buffer flip -- writes ten display-list high
bytes per branch as ten `LDA #`/`STA` pairs where the value changes only twice.
Loading each distinct value once frees **28 bytes**, left as a zero pocket at
`$4540`-`$455B` so `dat_455C` and everything after it stay put.

It was played, not just built. Over a **22,215-frame recorded session** ending
with the Ram boss beaten, against the stock cartridge on the same recording:

| | compacted | stock |
|---|---|---|
| display list in a valid pattern | 21,998 frames | 22,007 |
| isolated odd frames during play | 31 | **22** |
| odd frames during boot | 183 | **183** |
| buffer alternations | 17,002 | 16,686 |
| **writes into the pocket** | **0** | **0** |

The odd frames are single-frame samples caught while the flip is mid-write or a
different screen's list is installed; **the stock cartridge does the same thing**,
so they are a property of the game rather than of the change. No two are
consecutive in either build.

Nothing writes into the freed bytes in either cartridge, so they are genuinely
dead space.

#### What the first test got wrong

An earlier replay comparison showed the two diverging permanently from frame 245
and concluded the change was unsafe. That was a misreading. The routine leaves
A, X, Y and every RAM byte identical and performs the same ten writes in the
same order; what changes is cycle count, and the random generator mixes scratch
RAM (`$42`, `$44`, `$46`, `$55`) whose contents depend on timing. So the two
cartridges take different random paths from the same inputs -- **different, not
broken**, which a frame-by-frame state comparison cannot tell apart.

Padding with `NOP`s to restore the exact cycle count did not resolve the
divergence either, which should have been the clue: if matched cycles still
diverge, the measurement rather than the patch was at fault.

**42 bytes were found inside timing-critical code and excluded** -- the DLI
chain, the NMI path, the calibrated delay loop at `f7:$D0A5` and the text
renderer. They are counted separately and left alone.

## How claims are qualified

Documentation here distinguishes three kinds of statement, and the distinction
is load-bearing:

* **traced** -- read from instructions, with the address given
* **measured** -- observed on a running machine, with the method given
* **observed** -- taken from play or from a screenshot, marked as such

Where a claim rests on a rule generalised from another case, that is stated.
Where a number is derived rather than read, that is stated too.

## What is still open

Nothing structural. What remains is soft:

* **Timbre by ear.** All seven referenced instruments are characterised by role,
  pitch range, note length and waveform, and each is rendered playing its own
  notes -- but nobody has sat with the WAVs and named the sounds.
* **The nine unused instrument rows** are no longer a blank. Eight of the nine
  never release to silence, so a melody played through one has no gaps between
  notes and reads as a continuous hum rather than a tune -- which is why the
  score uses the other seven. Two of them are byte-identical. What the data
  still does not settle is intent: pad and effect shapes kept deliberately, or
  drafts left in place. See `SOUND.md`.
* **Two hitbox marks on the boss page** are placed from play rather than derived.
  A boss portrait narrower than the screen leaves its window origin
  underdetermined; Dr Evil's portrait fills the screen exactly and his marks do
  derive.
* **`b3:$8039`, `f6:$4E6D` and `f7:$F170`** pass a song number in a register.
  All three are accounted for by the area-type mechanism, but the register is
  not traced to a constant at each site.

The rebuild is byte-identical to the cartridge, which bounds all of this: no
claim here can be hiding a misread instruction, only a misread intention.

## Checking the "no missed code" claim mechanically

`disasm.py --check-gaps` scans for a `JSR`/`JMP` whose operand lands in a range
the recursive descent never reached, and classifies each candidate rather than
listing them raw. On its own that scan is close to useless -- `$20`, `$4C` and
`$6C` are ordinary byte values that occur constantly inside graphics and tables
and as the second or third byte of longer instructions, so the coincidences
swamp the real sites. This run finds **147 of them and one real call**.

Two things make it worth running. The tracer already knows every address that
is the first byte of an instruction, so a candidate whose opcode byte is not
one of those is not an instruction at all. And for `JMP ($xxxx)` the operand is
the *pointer*, not the target, so it is dereferenced -- which matters here more
than in most games, because this one's display-interrupt chain runs on RAM
vectors and a scan comparing the operand against the gap list would be asking
about the wrong address every time. Those two sites are reported separately:

    f6:400C  JMP ($2135)     the DLI chain
    f6:7590  JMP ($1FAC)     the music player's per-voice vector

### What it found

    b5:B460  JSR $B687   <-- reached by the tracer, target never disassembled

`sub5_B45C` tests `ram_00C8`, branches past the call when it is zero, and
otherwise calls `$B687`. The bytes there are a coherent routine:

    b5:B687   DEC $C8
    b5:B689   BPL +5
    b5:B68B   LDA #$00
    b5:B68D   STA $C8
    b5:B68F   RTS

A decrement-and-clamp on the same variable the caller guards on, which is
exactly what the guard implies. It is neither code nor a declared block in the
listing, so the coverage figures above are short by those bytes.
