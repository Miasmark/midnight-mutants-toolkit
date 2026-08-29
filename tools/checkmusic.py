#!/usr/bin/env python3
"""
Check music.py's reading of the songs against what the game's own player does.

    python tools/checkmusic.py <rom.a78> --log capture.log

`music.py` is a re-implementation: it parses the song tables and models the
player. That is what the editor previews through, and it is checked note for
note against the same parse -- so a misreading shared by both would be
invisible. This checks it from the other side, against the register writes the
cartridge's own player produces.

WHERE THE LOG COMES FROM

    Either capture works, and they agree:

      MAME       mame a7800 -cart rom.a78 -sound none -video none -str 40 \\
                      -autoboot_script <toolkit>/probes/audio.lua
      no MAME    python <toolkit>/tools/sim.py rom.a78 --seconds 40 -o out.log

    The second runs the cartridge's 6502 directly. On this cartridge it
    reproduces a MAME capture at 99% agreement with the frame clock exact, so
    the audio trace does not need an emulator installed.

WHAT IS COMPARED

    A note's second byte carries pitch and timbre together: the chip keeps
    bits 0-4 for AUDF and the player shifts the top three out to pick AUDC.
    The player writes the WHOLE byte, so the byte in the log is the byte in
    the song data, and the two can be compared directly with nothing modelled
    in between.
"""
import argparse
import os
import re
import subprocess
import sys


def read_log(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 7:
            rows.append(parts[1:7])
    return rows


def voice_stream(rows, idx):
    """The AUDF bytes a voice was given, in order, silences and repeats dropped."""
    out = []
    for v in rows:
        b = v[idx]
        if b != "00" and (not out or out[-1] != b):
            out.append(b)
    return out


def song_notes(rom, song):
    here = os.path.dirname(os.path.abspath(__file__))
    d = subprocess.run([sys.executable, os.path.join(here, "music.py"),
                        rom, "--song", str(song), "--dump"],
                       capture_output=True, text=True).stdout
    halves = d.split("voice 1")
    return (re.findall(r"\$([0-9A-F]{2}) = wave", halves[0]),
            re.findall(r"\$([0-9A-F]{2}) = wave", halves[1]) if len(halves) > 1 else [])


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("rom")
    ap.add_argument("--log", required=True, help="an audio capture of this cartridge")
    ap.add_argument("--songs", type=int, default=11)
    ap.add_argument("--run", type=int, default=5,
                    help="how many consecutive notes must line up to call it a match")
    args = ap.parse_args()

    rows = read_log(args.log)
    played = {"voice 0": voice_stream(rows, 1), "voice 1": voice_stream(rows, 4)}
    print("what the cartridge's own player wrote (AUDF bytes, in order):")
    for name, s in played.items():
        print("  %-8s %s%s" % (name, " ".join(s[:16]), " ..." if len(s) > 16 else ""))
    if not any(played.values()):
        print("\nThe log has no note data. A passive capture only reaches the "
              "music the game plays on its own; drive the fire button, or "
              "capture for longer.")
        return 1

    print("\nagainst music.py's parse:")
    hits = 0
    for song in range(args.songs):
        n0, n1 = song_notes(args.rom, song)
        for name, s in played.items():
            for pred, which in ((n0, "voice 0"), (n1, "voice 1")):
                if len(s) >= args.run and pred and \
                        " ".join(s[:args.run]) in " ".join(pred):
                    print("  song %-2d %s reproduces the player's %s"
                          % (song, which, name))
                    hits += 1
    if not hits:
        print("  no song's notes line up with what the player wrote.")
        print("  Either the capture covers music this parse does not cover,")
        print("  or the parse is wrong. Both are worth knowing; neither is")
        print("  decided by this script.")
        return 1
    print("\n%d agreement%s. The parse the editor previews through is doing "
          "what the cartridge does." % (hits, "" if hits == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
