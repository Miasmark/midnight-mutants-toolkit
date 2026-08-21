# Midnight Mutants -- sound

There are **two independent engines**, and they own one TIA channel each:

| | where | channel | drives |
|---|---|---|---|
| **sound effects** | `b0:$A018` | 0 | `AUDV0` / `AUDC0` / `AUDF0` |
| **music** | `f6:$752C`-`$7733` | 0 and 1 | `AUDV0,X` / `AUDC0,X` / `AUDF0,X` |

The music player addresses TIA **indexed by voice number**, so `STA AUDF0,X`
with X=1 is the write to `AUDF1`. A search for the literal symbols `AUDC1`,
`AUDF1` and `AUDV1` finds nothing but the silence routine; the engine only shows
up in a scan for `STA abs,X` against the audio page.

The two engines share channel 0 with no arbitration, and the way they collide is
asymmetric -- see "What happens when both engines want channel 0" below.

# Part 1 -- sound effects

A small byte-stream interpreter in bank 0.

## Interface

Bank 0 opens with a jump table, all three entries called from bank 6:

| vector | target | called from | what |
|---|---|---|---|
| `$A000` | `$A009` | `f6:$40E3`, `f6:$40F8` | silence: zero `AUDV0/1`, `AUDC0/1`, `AUDF0/1` |
| `$A003` | `$A018` | `f6:$4E41` | the per-frame tick |
| `$A006` | `$A19E` | `f6:$4E41` region | **not sound at all** -- this is the Grampa screen |

## Requesting a sound

Writing an effect id to `sfx_request` (`$1AF8`) is the whole interface. The tick
picks it up, looks the id up in a pointer table and clears the request:

    LDA sfx_request
    BEQ already_playing
      ASL A : TAX
      LDA dat0_A05C,X : STA $CD      ; stream pointer, low
      LDA dat0_A05D,X : STA $CE      ; and high
      LDA #$00 : STA sfx_request

A request always replaces whatever is playing -- there is no priority and no
mixing. Only channel 0 is driven here.

## The stream format

Each effect is a byte stream, read from the pointer until a terminator:

| byte | meaning |
|---|---|
| `$00` | end: silence `AUDV0` and clear the pointer |
| `< $10` | set `AUDC0` -- the waveform -- and **keep reading** |
| `>= $10` | one frame's worth: the byte goes to `AUDF0`, and its high nibble to `AUDV0`. Stop for this frame. |

So control bytes are free and pitch bytes cost a frame. A single byte carries
both volume and frequency: the whole byte is the frequency divisor, the top four
bits are the volume. Streams run 7 to 24 bytes, which at one pitch byte per
frame is roughly a tenth of a second to half a second.

## Three effects nothing plays

The streams sit end to end in one block, `b0:$A085`-`$A16E`. Walking it finds
**15 streams; the pointer table names only 12.** Three are unreachable:

| at | bytes | notes |
|---|---|---|
| `$A0AF` | 17 | `01 91 91 91 71 51 31 8E 4E 2E ...`, waveform `$01` |
| `$A0DF` | 16 | `0C E7 E7 E8 E9 EA EC ED EF F2 ...` |
| `$A0EF` | 34 | `06 90 90 50 30 92 92 52 32 94 ...` |

Two are near-twins of shipped effects. `$A0DF` opens the same way as `$A156`,
the killing blow, on a different waveform (`$0C` against `$08`); `$A0EF` is the
same opening as `$A111`, the projectile impact, but 34 bytes against 26. They
read as earlier takes that were replaced rather than deleted.

They are reachable again by pointing an id at one -- confirmed on hardware.
Aiming the item-collected id `$08` at `$A0EF` and replaying a pickup, the audio
registers take `AUDC0 = $06` then `90 90 50 30 92 92 52 ...` instead of the
stock `AUDC0 = $04` then `88 88 88 67 67 47`.

This also sizes an edit: a stream may grow over anything after it that no id
points at, and stops at the next stream something plays.

## The effects

Twenty ids, `$00`-`$13`. Named from their call sites:

| id | stream | used by |
|---|---|---|
| `$00` | -- | silence |
| `$01`-`$04` | `$A085` | **weapon fire** -- `sfx_request = weapon_level + 1` at `f6:$5048` |
| `$08` | `$A08D` | item collected (`f6:$51F0`) |
| `$09` | `$A095` | item collected, second variant (`f6:$51FF`) |
| `$0A` | `$A0C0` | the well of health (`f6:$57A9`) |
| `$0B` | `$A0D1` | a gated item released once the room is cleared (`f6:$52BA`) |
| `$0C` | `$A111` | projectile impact (`f6:$59AD`) |
| `$0D` | `$A09F` | the player taking contact damage (`f6:$5FBE`, `$5FF2`, `$603C`, `b5:$BBCC`) |
| `$0F` | `$A12B` | a potion used (`f6:$5081`, `$50A5`) |
| `$10` | `$A13A` | a boss hit (`f6:$6678`, `b5:$B50D`) |
| `$11` | `$A14C` | hurting ground and special-actor contact (`f6:$57A3`, `$6730`) |
| `$12` | `$A156` | **the killing blow** (`f6:$5DB3`) |
| `$13` | `$A165` | **a hit the actor survived** (`f6:$5D99`) |

`$12` and `$13` are the two halves of one decision at `f6:$5D86`, the projectile
damage site:

    LDA actor_mode,X
    CMP #$A0 : BCS died        ; already over the threshold
    ADC weapon_level           ; damage is the weapon level
    STA actor_mode,X
    CMP #$A0 : BCS died        ; crossed it now
      LDA #$13 : STA sfx_request     ; survived -- and flash for $1E frames
      ...
    died:
      LDA #$12 : STA sfx_request     ; killed

So `actor_mode` doubles as an accumulating damage counter that kills at `$A0`,
and the two sounds tell the player whether a shot was fatal.

**All four weapons share one firing sound.** `sfx_request` is set to
`weapon_level + 1`, giving ids 1 through 4, and every one of those table entries
points at the same stream at `$A085`. The knife, axe, blaster and mega blaster
are audibly identical.

Ids `$05`, `$06`, `$07` and `$0E` have null pointers and are never requested.

# Part 2 -- music

A two-voice tracker in the fixed bank. Two trampolines sit at the very top of
bank 6 so any bank can reach them:

| | | |
|---|---|---|
| `f6:$4006` | `MusicPlay(A = song)` | called from b0, b3, b5, f6, f7 |
| `f6:$4009` | `MusicTick()` | once per frame |

`MusicTick` silences both channels when `music_song` (`$1FAE`) is `$FF`,
otherwise steps each enabled voice.

## Three levels of data

    SongTable  ->  track (list of patterns)  ->  pattern (list of notes)

**`SongTable`** (`f6:$7F65`) is 4 bytes per song: a voice 0 track pointer and a
voice 1 track pointer. Either may be null, and a song with one null voice is
mono.

**A track** is a list of 16-bit pattern pointers ending at a `$00` high byte.
The low byte of that terminator says what happens next:

| terminator | |
|---|---|
| `$00` | loop this song from the top |
| `$80`-`$FF` | stop; `music_song` = `$FF` |
| other *n* | chain to song *n*-1, recorded in `music_next_song` |

**A pattern** is a count byte followed by that many 2-byte notes:

    byte 0   instrument (high nibble) | duration index (low nibble)
    byte 1   waveform (top 3 bits) | frequency (low 5 bits) -- 0 means rest

Duration index reads `NoteDurTable` (`$7734`), a clean halving sequence
`96 72 64 48 36 32 24 18 16 12 9 8 6 4 3 2` in frames.

### Byte 1 carries timbre and pitch at once

`AUDF` is a **5-bit** register. The player writes the whole byte to it and the
chip keeps only bits 0-4 -- then shifts the same byte right by five and uses the
three bits the chip discarded to pick the waveform:

    STA AUDF0,X        ; the chip keeps bits 0-4
    LSR A  (x5)        ; the top 3 bits it threw away...
    TAY
    LDA WaveByPitch,Y  ; ...are the waveform selector
    STA AUDC0,X

`WaveByPitch` (`$76F6`) = `4 12 1 6 8 7 15 9`. This is not a "waveform per pitch
range" as it first appears -- it is one packed byte doing two jobs, and the
register width is what separates them.

The melody uses selectors 1 and 2, so `AUDC` 12 (pure tone divided by six) and
`AUDC` 1 (the 4-bit polynomial, a pitched buzz rather than noise). Decoded that
way every note lands on an exact semitone:

| selector 1, AUDC 12 | F3 D#3 D3 C3 A#2 A2 G2 F2 |
|---|---|
| **selector 2, AUDC 1** | **C3 A#2 A2 G2 F2 D#2 D2 C#2 C2** |

Both are the same minor scale in two registers, which is the confirmation that
the split is read correctly -- a wrong split gives frequencies scattered between
semitones.

## Pointers are bank-relative

A track pointer in `$8000`-`$BFFF` lands in the paged window and is read against
**whatever bank is mapped when the song starts**. Song 3 and song 5 both point
at `$BE00`; song 3 is started from bank 0 and song 5 from bank 5, so they are
different tunes at the same address. Each bank carries its own music.

This is why the songs never showed up in a search of the fixed bank -- half of
them are not in it.

## The songs

| song | voice 0 | voice 1 | started at | what |
|---|---|---|---|---|
| **0** | -- | `$8C18` bank 3 | intro script `+1` | **intro**, first cue, 24 notes, stops |
| **1** | -- | `f6:$78A7` | (variable) | **main theme**, 200 notes, chains to 2 |
| **2** | -- | `f6:$785A` | (variable) | **main theme part 2**, chains back to 1 |
| 3 | `$BE00` bank 0 | `$BE04` bank 0 | `b0:$A226` | Grampa screen, 34 notes, stops |
| **4** | `$8C00` bank 3 | `$8C04` bank 3 | `b3:$8069` | **title screen**, loops |
| 5 | `$BE06` bank 5 | `$BE00` bank 5 | `b5:$B0D2`, `$B0FC` | **boss fight**, 100 + 56 notes, loops |
| **6** | `$8C08` bank 3 | `$8C10` bank 3 | intro script `+74` | **intro**, second cue, 145 notes, stops |
| 7 | `f6:$786E` | `f6:$7872` | `b5:$B52A` | boss defeated |
| **8** | -- | `f6:$7876` | area pages 3, 4, 8 | **the cave music**, 315 notes, loops |
| **9** | -- | `f6:$787C` | area page 7 | **the cave music**, second tune, 304 notes, loops |
| **10** | `f6:$7896` | `f6:$789A` | area type `$0A` | **the funeral dirge** -- death / game over |
| 11 | -- | -- | `b0:$A315` | silence |

## The graphics page picks the music

`f7:$F13E` loads `area_page` (`$1FCF`) and uses it to index three tables in a
row -- `tbl_AreaPtrLo`, `tbl_AreaPtrHi`, then `tbl_AreaType` (`$FED9`), whose
value goes straight into `music_next_song`. There is no music-per-room table.
**The same byte that selects a room's artwork selects its music**, which is why
rooms that look alike always sound alike.

| area page | 0 | 1 | 2 | 3 | 4 | 7 | 8 |
|---|---|---|---|---|---|---|---|
| song | 0 | 1 / 2 | 1 / 2 | 8 | 8 | 9 | 8 |
| rooms | -- | 19 | 16 | 5 | 2 | 18 | 16 |

Pages 1 and 2 are the surface world and carry the main theme; `f7:$F152` tests a
bit of `$1FBD` and adds one, choosing song 1 or song 2 between its two halves.

Pages 7 and 8 are the caves -- 34 rooms between them, the largest single block
in the game and the part hardest to map. Page 7 plays song 9 and page 8 plays
song 8. Pages 3 and 4 (the crypt, cemetery, basement, church and barn) play song
8 as well, so the enclosed interiors share the cave music with the caves proper.

Music only changes when the new song differs from the one playing
(`CPY music_song / BEQ`), so walking between two areas of the same page does not
restart the tune. Death is suppressed explicitly: `LDA death_state / BNE` skips
the change, so the dirge is not interrupted by the room you died in.

### The dirge

`CheckDeathCondition` (`f6:$4E70`) switches `area_type` to `$0A` when `hp_cur`
or `blood_purity` reaches zero, which selects song 10 through the same
mechanism as every other area.

It is short only in note count. Voice 1 tolls two low notes -- **F2 and C#2**,
48 frames each -- six times over, while voice 0 carries a slow F2 line falling
through G#2 and G2. Both voices run **exactly 384 frames** and end together on a
held 96-frame note: 6.4 seconds, and the only track in the game whose two voices
are written to the same total length.

**Songs 1 and 2 chain to each other**, so the main theme is a two-part loop that
never terminates. Songs 8 and 9 are separate adjacent tracks that each loop on
their own -- song 9 does it by naming itself as the chain target rather than
using the `$00` loop terminator.

## The intro is a script

`b3:$802C` interprets a byte stream at `dat3_8762`, and the music cues are
entries in it rather than calls placed in code:

| byte | |
|---|---|
| `< $40` | show display frame *n* |
| `$40`-`$7F` | `MusicPlay(n & $0F)` |
| `$80`-`$FD` | wait `(n & $7F) + 1` units |
| `$FE` | clear flag `$93` |
| `$FF` | end |

The script is 94 display commands and 113 wait units: an eight-times repeat of
frames 1-2-3, then 4 4 5 5 6, then 7-8 alternating. Song 0 starts at the very
top, song 6 comes in at offset 74, and the `$FF` at the end falls straight into
`LDA #$04 : JSR MusicPlay` -- the title music, which loops while the title
screen waits for a button. Leaving the title zeroes `AUDC0` and `AUDC1`
directly at `b3:$8088`.

**This is how song 0's bank was resolved.** Its tracks are paged, and the call
site passes the song number in `A`, so it could not be read until the script
that drives it was found; the script runs with bank 3 mapped, as do songs 4
and 6.

## The envelope

Each voice runs a five-stage ADSR, held in `music_env_state` (`$1FB0,X`) and
dispatched through `JMP (music_env_vec)`. **The five handlers are reached only
by that indirect jump**, so a static tracer walks straight past them; they are
declared as entry points in `annotations.json`.

| state | at | |
|---|---|---|
| 0 | `$759D` | attack -- add the increment, clamp at peak |
| 1 | `$75CF` | decay -- subtract, floor at the sustain level |
| 2 | `$75FB` | sustain -- hold, just count down |
| 3 | `$760A` | release -- subtract, floor at zero |
| 4 | `$762A` | done -- `AUDV = 0` |

`music_vol` (`$1FB8,X`) is an **8-bit** accumulator whose *high* nibble is
written to the 4-bit `AUDV`, giving sub-step resolution on the ramps.

`InstrTable` (`$7744`) is 16 bytes per instrument, selected by the note's high
nibble, so there are 16 slots and **all 16 are populated** (14 and 15 are
identical duplicates). Ten bytes of each row are used:

| offset | |
|---|---|
| +0 | flags ORed into `AUDV`; low nibble is the starting volume |
| +1 | initial stage counter |
| +2 | peak volume |
| +3 | attack increment |
| +4 | decay stage length |
| +5 | sustain level |
| +6 | decay decrement |
| +7 | sustain stage length |
| +8 | release stage length |
| +9 | release decrement |

## Seven instruments carry the score, and the other nine cannot

Counted across all eleven songs, the notes name **7 of the 16 rows**:

| instrument | notes | | instrument | notes |
|---|---|---|---|---|
| 0 | 432 | | 5 | 164 |
| 1 | 149 | | 9 | 71 |
| 2 | 372 | | 12 | 40 |
| 3 | 177 | | | |

The other nine are never selected. What separates them is not timbre -- the
waveform comes from the note's own byte, not from the instrument -- but whether
the envelope **reaches zero before the note's frames run out**.

That is where articulation comes from. Instrument 2 runs `8 8 4 1 0 0 0 ...`:
silent from frame four, so a sixteen-frame note is four frames of sound and
twelve of silence, and the next note starts against a gap. Instruments 1 and 12
do the same. Those three are the melodic voices.

Now the sustain levels, measured over 90 frames:

| | falls silent | holds at a non-zero level |
|---|---|---|
| the 7 used | 3 | 4 |
| the 9 unused | **1** | **8** |

Eight of the nine unused rows never release. Their decay floors sit at 2, 3, 4,
6 and 8 and they stay there for as long as the note lasts, so a melody played
through one of them has no gaps at all: each note runs straight into the next at
constant volume.

**That is why they sound like an engine rather than a tune.** The songs are
already mostly buzz and noise -- of 1,405 sounding notes, 458 select the 4-bit
polynomial, 259 the 9-bit (white noise) and 157 the 5-bit, against 531 square.
Articulation is the only thing making that read as melody, and these rows remove
it. The differences between them are the various hums: instrument 10 oscillates
between 6 and 7 every few frames, 11 spikes to `$F` before settling at 8, and 13
blips to `$C` and then holds flat.

Two further marks against them being a usable library: **14 and 15 are
byte-identical**, and only 15 of the 16 rows are distinct.

*Observed first by ear -- converting song notes onto the unused rows in the
editor -- then traced to the envelope tables.*


Instrument 0, which carries the main melody, reads
`80 01 80 80 08 05 06 FF 80 00`: an instant attack to volume 8, a short decay to
5, then a sustain counter of `$FF` and a release decrement of **zero** -- it
never fades on its own, it simply holds until the next note.

A rest takes a shortcut: `MusicNoteOn` sets state 4 directly and loads the
release counter, so the voice is cut rather than ramped down.

## What happens when both engines want channel 0

`sub_40D8` runs the effect tick first and the music tick second, in the same
frame. That ordering alone does not decide the outcome, because the two engines
write different registers at different rates:

| register | effects | music |
|---|---|---|
| `AUDF0` / `AUDC0` | every frame the effect is playing | **only at note-on** |
| `AUDV0` | every frame | every frame **except sustain** (state 2) |

Two consequences follow, both audible:

* **An effect retunes the music.** Music sets `AUDF0` only when a note starts,
  so an effect's pitch writes stand until the melody's *next* note begins.
* **An effect leaves a hole behind it.** The end of a stream writes `AUDV0 = 0`
  (`b0:$A053`). If the music note is sitting in sustain, which does not write
  `AUDV0`, channel 0 stays silent until the next note-on.

Instrument 0 -- the melody instrument -- has a sustain length of `$FF`, so its
notes spend nearly all their time in exactly the state that does not rewrite
volume. The effect wins by default.

### The music is written around this

Every song that plays during ordinary exploration is **mono on voice 1**:

| voice 1 only | songs 0, 1, 2, 8, 9 -- intro cue, main theme, both cave tunes |
|---|---|
| both voices | songs 3, 4, 5, 6, 7, 10 -- Grampa, title, boss, intro, victory, dirge |

Channel 0 is left empty exactly when the player is walking around setting off
sound effects, and both voices are used in the screens where few or no effects
play. The one exception is the boss fight, song 5, which does use both voices
in a context full of hit sounds.

## Tempo

`sub_40D8` runs the effect tick (`sub0_A003`) and then `MusicTick` in the same
frame update, and the `mode_flag` branches are arranged so that **exactly one**
`MusicTick` happens per frame on either path. So a duration index is a count of
frames at 60 Hz: the melody's alternating 16 and 8 frames are about 0.27 s and
0.13 s, or roughly 112 BPM.

## Listening to it

`tools/music.py` reads the tables above and renders a song to a WAV, with a TIA
model that implements the real polynomial counters and the actual ADSR from
`$759D`.

Two details decide whether the output is music or noise:

* **`AUDF` must be masked to five bits.** The note byte carries the waveform in
  its top three, and feeding the whole byte to the frequency divider puts every
  note about three times too low.
* **The polynomial counters need XOR feedback and a non-zero seed.** XNOR
  feedback with an all-ones register sits in that construction's lockup state:
  the register never advances, the voice outputs flat DC, and all that remains
  audible is the envelope stepping the volume once a frame.

Correctness is checked by measuring the rendered audio rather than trusting it:
each note's period is compared against the frequency the tables predict, and
agrees to within a fraction of a percent, while a deliberately wrong period
falls to chance.

    python tools/music.py <rom.a78> --list
    python tools/music.py <rom.a78> --song 1 --dump
    python tools/music.py <rom.a78> --song 1 -o build/music/song1.wav

The main theme comes out at 62 seconds across its two chained halves.

## Not covered

Every song is now placed. The two call sites that pass the song number in `A`
are both the area-type mechanism above: `f7:$F170` starts the area's tune on a
change, and `f6:$4E6D` re-starts `music_next_song` when a chained song has run
out and the area's tune should resume.

Bank 0 remains 7.5% traced.

## What each instrument does

Only **seven of the sixteen rows are ever referenced**. An envelope on its own
says little; what matters is what it reaches inside the note lengths the songs
actually use, and which voice it plays on.

| inst | notes | songs | voice | AUDF | note | waveform | role |
|---|---|---|---|---|---|---|---|
| 0 | 432 | 1 2 4 7 10 | both | 11-31 | 12 | pure tone /6 | **the lead** -- the main theme, title, victory and the dirge all carry it |
| 1 | 149 | 2 5 7 | 1 only | 10-31 | 12 | 4-bit poly | a second melodic voice, buzzed rather than clean |
| 2 | 372 | 0 5 9 | both | **2-26** | 12 | **9-bit poly** | noise at high pitch -- percussion, and the second most used row in the game |
| 3 | 177 | 8 | 1 only | 14-31 | 12 | pure tone /6 | the cave theme's melody, and nothing else |
| 5 | 164 | 3 6 | both | 14-31 | **6** | 4-bit poly | short notes under the Grampa screen and the intro |
| 9 | 71 | 6 | both | 10-31 | **3** | pure tone /6 | very short notes in the intro's second cue |
| 12 | 40 | 9 | 1 only | **1-10** | 12 | **9-bit poly** | noise at the very top of the range -- a hiss over the cave music |

Rows 4, 6, 7, 8, 10, 11, 13, 14 and 15 are never used by any song; 14 and 15 are
byte-identical to each other.

`tools/music.py` renders each row playing **its own notes**, taken from the song
where it appears most: `build/music/instruments/inst_NN.wav`.

### An envelope only matters if the note lasts

Instrument 9's row can climb to volume 15, which makes it look like the outlier
of the set -- a long dramatic swell. It is not. Its attack increment is `$01`
against a `$7F` counter, so reaching the top takes about 103 frames, and **its
notes are three frames long**:

    inst   median note   envelope could reach   actually reaches
      0      12 frames            8                    8
      9       3 frames           15                    8   <- never gets there

Every other row completes inside its own notes. In practice instrument 9 is a
flat volume-8 voice and the swell written into it is never heard. Reading the
instrument table without checking it against the music it plays gives exactly
the wrong impression of that row.
