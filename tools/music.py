#!/usr/bin/env python3
"""
Read the music out of the cartridge, and render it to a WAV so it can be
checked against the real thing.

The player lives in the fixed bank at f6:$752C-$7733 and drives both TIA
channels through indexed stores (STA AUDF0,X with X as the voice number).
Data is three levels deep:

    SongTable ($7F65)  4 bytes/song: voice 0 track ptr, voice 1 track ptr
      track            list of 16-bit pattern pointers, ends at a $00 high byte
        pattern        count byte, then that many 2-byte notes
          note         byte 0 = instrument<<4 | duration index
                       byte 1 = waveform<<5 | 5-bit frequency, 0 = rest

AUDF is a 5-bit register. The player writes the whole of byte 1 to it and the
chip keeps only bits 0-4; the top three bits, which the chip discards, are
shifted out and used to index WaveByPitch for AUDC. So one byte carries both
the timbre and the pitch.

A track pointer in $8000-$BFFF is read against whatever bank is mapped when the
song starts, so a song is identified by (song number, bank).

Usage:
  python music.py <rom.a78> --list
  python music.py <rom.a78> --song 1 --dump
  python music.py <rom.a78> --song 1 -o build/theme.wav
"""
import argparse
import os
import struct
import wave

BANK_SIZE = 16384
SONG_TABLE = 0x7F65
DUR_TABLE = 0x7734
WAVE_BY_PITCH = 0x76F6
INSTR_TABLE = 0x7744

# NTSC TIA audio divider clock: 3.58 MHz / 114.
TIA_CLOCK = 31400.0
FRAME_RATE = 60.0
SAMPLE_RATE = 44100

# Which bank is mapped when each song is started, taken from the call sites in
# the disassembly. This only matters for songs whose track pointers land in the
# paged $8000-$BFFF window; songs whose tracks are in the fixed bank play the
# same wherever they are started from, and are marked None here.
#
# Song 0 is started by the intro script at b3:$8762, which runs with bank 3
# mapped -- so its paged tracks resolve against bank 3, as do songs 4 and 6.
SONG_BANK = {0: 3, 1: None, 2: None, 3: 0, 4: 3, 5: 5, 6: 3,
             7: None, 8: None, 9: None, 10: None, 11: None}
SONG_NAME = {
    0: "intro, first cue", 1: "main theme (chains to 2)",
    2: "main theme part 2 (chains to 1)", 3: "Grampa screen",
    4: "title screen (loops)", 5: "boss fight",
    6: "intro, second cue", 7: "boss defeated",
    8: "cave music (area pages 3, 4, 8)", 9: "cave music (area page 7)",
    10: "the funeral dirge -- death / game over", 11: "silence",
}


class Unresolved(Exception):
    """A paged track pointer whose bank is not known."""
    def __init__(self, addr):
        Exception.__init__(self, "$%04X needs a known bank" % addr)


class Rom:
    def __init__(self, path):
        raw = open(path, "rb").read()
        self.hdr = 128 if len(raw) % BANK_SIZE else 0
        self.raw = raw

    def bank(self, n):
        return self.raw[self.hdr + n * BANK_SIZE: self.hdr + (n + 1) * BANK_SIZE]

    def read(self, addr, bank):
        """Read one byte as the running game would see it.

        $4000-$7FFF is always the fixed bank 6. $8000-$BFFF is the paged window
        and resolves against `bank`. $C000+ is the fixed bank 7.
        """
        if 0x4000 <= addr < 0x8000:
            return self.bank(6)[addr - 0x4000]
        if 0x8000 <= addr < 0xC000:
            if bank is None:
                raise Unresolved(addr)
            return self.bank(bank)[addr - 0x8000]
        if addr >= 0xC000:
            return self.bank(7)[addr - 0xC000]
        raise ValueError("address $%04X is RAM, not ROM" % addr)

    def word(self, addr, bank):
        return self.read(addr, bank) | (self.read(addr + 1, bank) << 8)


def song_tracks(rom, song):
    a = SONG_TABLE + song * 4
    return rom.word(a, 6), rom.word(a + 2, 6)


def read_track(rom, ptr, bank, limit=64):
    """Pattern pointers until a $00 high byte. Returns (patterns, terminator)."""
    pats = []
    while len(pats) < limit:
        lo = rom.read(ptr, bank)
        hi = rom.read(ptr + 1, bank)
        if hi == 0:
            return pats, lo
        pats.append(lo | (hi << 8))
        ptr += 2
    return pats, None


def read_notes(rom, pat, bank):
    """A pattern: count byte, then that many (byte0, pitch) pairs."""
    n = rom.read(pat, bank)
    out = []
    for i in range(n):
        b0 = rom.read(pat + 1 + i * 2, bank)
        b1 = rom.read(pat + 2 + i * 2, bank)
        out.append((b0, b1))
    return out


def voice_notes(rom, ptr, bank):
    """Flatten one voice's whole track into (instrument, frames, pitch)."""
    if not ptr:
        return [], None
    if 0x8000 <= ptr < 0xC000 and bank is None:
        return None, None
    pats, term = read_track(rom, ptr, bank)
    out = []
    for p in pats:
        for b0, pitch in read_notes(rom, p, bank):
            frames = rom.read(DUR_TABLE + (b0 & 0x0F), 6)
            out.append((b0 >> 4, frames, pitch))
    return out, term


# --------------------------------------------------------------- TIA synthesis
# The polynomial counters. AUDC selects which of these clocks the output and
# how far the frequency divider is stepped down first.
def poly(bits, taps, length):
    """A maximal-length LFSR: XOR of the taps shifted back in at the top.

    The feedback must be XOR with a non-zero seed. Using XNOR with an all-ones
    seed lands on that construction's lockup state -- the register never
    changes, the "waveform" is flat DC, and the only thing left to hear is the
    envelope stepping the volume once a frame, which sounds like tapping.
    """
    reg, out = (1 << bits) - 1, []
    for _ in range(length):
        out.append(reg & 1)
        fb = 0
        for t in taps:
            fb ^= (reg >> t) & 1
        reg = (reg >> 1) | (fb << (bits - 1))
    return out


POLY4 = poly(4, (0, 1), 15)
POLY5 = poly(5, (0, 2), 31)
POLY9 = poly(9, (0, 4), 511)
DIV31 = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


# For each AUDC: the bit pattern the output stage walks, and how many divided
# clocks each step of that pattern takes. A pure tone is just the pattern [1,0],
# so its period is 2 steps; "div 6" means each step takes 6 clocks, giving the
# familiar period of 12.
SQUARE = [1, 0]
AUDC_MODE = {
    0x00: (None, 1), 0x0B: (None, 1),          # silence
    0x04: (SQUARE, 1), 0x05: (SQUARE, 1),      # pure tone
    0x0C: (SQUARE, 6), 0x0D: (SQUARE, 6),      # pure tone, div 6
    0x06: (SQUARE, 31), 0x0A: (SQUARE, 31),    # pure tone, div 31
    0x0E: (SQUARE, 93),                        # pure tone, div 93
    0x01: (POLY4, 1),                          # 4-bit poly -- pitched buzz
    0x02: (POLY4, 31),                         # 4-bit poly, div 31
    0x03: (POLY4, 31),                         # 5-bit poly gating 4-bit
    0x07: (POLY5, 1), 0x09: (POLY5, 1),        # 5-bit poly
    0x0F: (POLY5, 6),                          # 5-bit poly, div 6
    0x08: (POLY9, 1),                          # 9-bit poly -- white noise
}


def channel_stream(audc, audf, nsamples, phase):
    """Generate `nsamples` of +/-1 for one TIA channel.

    AUDF is a **5-bit** register: the game writes a whole byte, but the chip
    keeps only bits 0-4, and the top three bits are what the player shifts out
    to choose AUDC. Feeding the unmasked byte in here makes every note about
    three times too low -- the polynomial voices fall below the range where a
    pitch is heard at all and turn into a tapping noise.
    """
    table, pre = AUDC_MODE.get(audc, (POLY4, 1))
    if table is None:
        return [0] * nsamples, phase
    rate = TIA_CLOCK / ((audf + 1) * pre)
    step = rate / SAMPLE_RATE
    out = []
    for _ in range(nsamples):
        phase += step
        out.append(1 if table[int(phase) % len(table)] else -1)
    return out, phase


def envelope(rom, instr, frames):
    """Run the five-stage ADSR for one note, returning per-frame AUDV.

    Mirrors f6:$759D..$762E. music_vol is 8-bit; its high nibble is the 4-bit
    AUDV that actually reaches the chip.
    """
    row = [rom.read(INSTR_TABLE + instr * 16 + i, 6) for i in range(10)]
    vol = row[0] & 0x0F
    ctr = row[1]
    state = 0
    out = []
    for _ in range(frames):
        if state == 0:                                  # attack
            vol = min(vol + row[3], row[2])
            if ctr == 0:
                ctr, state, vol = row[4], 1, row[2]
            else:
                ctr -= 1
        elif state == 1:                                # decay
            vol = max(vol - row[6], row[5])
            if ctr == 0:
                ctr, state = row[7], 2
            else:
                ctr -= 1
        elif state == 2:                                # sustain
            if ctr == 0:
                ctr, state = row[8], 3
            else:
                ctr -= 1
        elif state == 3:                                # release
            vol = max(vol - row[9], 0)
            if ctr == 0:
                state = 4
            else:
                ctr -= 1
        else:
            vol = 0
        out.append(((vol >> 4) | row[0]) & 0x0F)
    return out


def render_voice(rom, notes, total_frames):
    buf = [0.0] * int(SAMPLE_RATE * total_frames / FRAME_RATE)
    at = 0
    phase = 0.0
    for instr, frames, pitch in notes:
        n = int(SAMPLE_RATE * frames / FRAME_RATE)
        if pitch:
            # the note byte packs waveform in the top 3 bits and the 5-bit
            # frequency divisor in the low 5 -- see channel_stream
            audc = rom.read(WAVE_BY_PITCH + (pitch >> 5), 6)
            wav, phase = channel_stream(audc, pitch & 0x1F, n, phase)
            env = envelope(rom, instr, frames)
            per = max(1, n // frames)
            for i in range(n):
                if at + i >= len(buf):
                    break
                v = env[min(len(env) - 1, i // per)] / 15.0
                buf[at + i] = wav[i] * v
        at += n
        if at >= len(buf):
            break
    return buf


def render(rom, song, path, repeats=1):
    bank = SONG_BANK.get(song, 6)
    v0, v1 = song_tracks(rom, song)
    n0, _ = voice_notes(rom, v0, bank)
    n1, _ = voice_notes(rom, v1, bank)
    f0 = sum(f for _, f, _ in n0)
    f1 = sum(f for _, f, _ in n1)
    total = max(f0, f1)
    if not total:
        print("song %d is empty" % song)
        return
    a = render_voice(rom, n0, total) if n0 else []
    b = render_voice(rom, n1, total) if n1 else []
    ln = max(len(a), len(b))
    a += [0.0] * (ln - len(a))
    b += [0.0] * (ln - len(b))
    mono = [(a[i] + b[i]) * 0.35 for i in range(ln)] * repeats
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in mono))
    print("song %d -> %s  (%.1f s, %d + %d notes)"
          % (song, path, ln * repeats / float(SAMPLE_RATE), len(n0), len(n1)))


def dump(rom, song):
    bank = SONG_BANK.get(song, 6)
    v0, v1 = song_tracks(rom, song)
    print("song %d  (%s)  %s"
          % (song, "bank %d" % bank if bank is not None else "fixed bank",
             SONG_NAME.get(song, "")))
    for vi, ptr in ((0, v0), (1, v1)):
        if not ptr:
            print("  voice %d: silent" % vi)
            continue
        pats, term = read_track(rom, ptr, bank)
        end = {0: "loop", 0xFF: "stop"}.get(term, "chain to song %d"
                                            % ((term or 1) - 1))
        if term is not None and 0x80 <= term < 0xFF:
            end = "stop"
        notes, _ = voice_notes(rom, ptr, bank)
        print("  voice %d: $%04X  %d patterns, %d notes, end = %s"
              % (vi, ptr, len(pats), len(notes), end))
        for i, (ins, fr, p) in enumerate(notes[:16]):
            if not p:
                print("      %2d  inst %X  %3d frames  rest" % (i, ins, fr))
            else:
                audc = rom.read(WAVE_BY_PITCH + (p >> 5), 6)
                print("      %2d  inst %X  %3d frames  $%02X = wave %d "
                      "(AUDC %2d) + AUDF %2d"
                      % (i, ins, fr, p, p >> 5, audc, p & 0x1F))
        if len(notes) > 16:
            print("      ... %d more" % (len(notes) - 16))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--song", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("-o", "--out")
    args = ap.parse_args()
    rom = Rom(args.rom)
    if args.list or args.song is None:
        for s in range(12):
            bank = SONG_BANK.get(s, 6)
            v0, v1 = song_tracks(rom, s)
            n0, _ = voice_notes(rom, v0, bank)
            n1, _ = voice_notes(rom, v1, bank)
            if n0 is None or n1 is None:
                print("  song %2d  paged, bank not yet known" % s)
                continue
            print("  song %2d  %-8s %3d + %3d notes   %s"
                  % (s, "bank %d" % bank if bank is not None else "fixed",
                     len(n0), len(n1), SONG_NAME.get(s, "")))
        return
    if args.dump:
        dump(rom, args.song)
    if args.out:
        render(rom, args.song, args.out, args.repeats)


if __name__ == "__main__":
    main()
