#!/usr/bin/env python3
"""Render assets/card.svg, the single image the profile README shows.

    python3 scripts/build_card.py            # fetch live GitHub data, write the card
    python3 scripts/build_card.py --static   # same, without animation (for screenshots)

Data sources:
  data/profile.json  name, tagline, accent, "now" lines, pinned-repo blurbs
  data/stack.json    tool logos, grouped (logo paths live in data/icons.json)
  data/tokens.json   AI token totals, pushed from the Mac by tally_tokens.py
  GitHub GraphQL     contributions, streaks, languages, pinned repos

Stdlib only. Needs GITHUB_TOKEN (falls back to `gh auth token` locally).
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "assets" / "card.svg"

W = 860          # card width
P = 28           # outer padding
SPLIT = 480      # x where two-column rows divide
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

BG, BORDER, INK, MID, DIM, FAINT, TRACK = (
    "#0b0b0c", "#262626", "#ededed", "#a3a3a3", "#666666", "#2c2c2c", "#161616",
)

# ---------------------------------------------------------------- pixel font
# A blocky, square-cornered 5x7 face. "#" is a lit pixel.
FONT = {
    "A": "#####|#...#|#...#|#####|#...#|#...#|#...#",
    "B": "####.|#..#.|#..#.|#####|#...#|#...#|#####",
    "C": "#####|#....|#....|#....|#....|#....|#####",
    "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####",
    "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": "#####|#....|#....|#.###|#...#|#...#|#####",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "###|.#.|.#.|.#.|.#.|.#.|###",
    "J": "....#|....#|....#|....#|#...#|#...#|#####",
    "K": "#...#|#..#.|#.#..|###..|#..#.|#...#|#...#",
    "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|##..#|#.#.#|#..##|#...#|#...#|#...#",
    "O": "#####|#...#|#...#|#...#|#...#|#...#|#####",
    "P": "#####|#...#|#...#|#####|#....|#....|#....",
    "Q": "#####|#...#|#...#|#...#|#.#.#|#..##|#####",
    "R": "#####|#...#|#...#|#####|#.#..|#..#.|#...#",
    "S": "#####|#....|#....|#####|....#|....#|#####",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|#####",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|#####",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|#...#|#####|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": "#####|#...#|#..##|#.#.#|##..#|#...#|#####",
    "1": "..#..|.##..|..#..|..#..|..#..|..#..|#####",
    "2": "#####|....#|....#|#####|#....|#....|#####",
    "3": "#####|....#|....#|.####|....#|....#|#####",
    "4": "#...#|#...#|#...#|#####|....#|....#|....#",
    "5": "#####|#....|####.|....#|....#|#...#|#####",
    "6": "#####|#....|#....|#####|#...#|#...#|#####",
    "7": "#####|....#|....#|...#.|..#..|..#..|..#..",
    "8": "#####|#...#|#...#|#####|#...#|#...#|#####",
    "9": "#####|#...#|#...#|#####|....#|....#|#####",
    ",": "..|..|..|..|.#|.#|#.",
    ".": ".|.|.|.|.|.|#",
    " ": "...|...|...|...|...|...|...",
    "-": "....|....|....|####|....|....|....",
    "/": "....#|....#|...#.|..#..|.#...|#....|#....",
    "'": "#|#|.|.|.|.|.",
    "?": "#####|....#|....#|..###|..#..|.....|..#..",
}
GLYPHS = {k: v.split("|") for k, v in FONT.items()}


def glyph(ch):
    return GLYPHS.get(ch.upper(), GLYPHS["?"])


def px_width(text, s):
    cols = sum(len(glyph(c)[0]) + 1 for c in text)
    return max(cols - 1, 0) * s


def px_path(text, x, y, s):
    """Path data for text in the pixel font, one rect per horizontal run."""
    d = []
    cx = x
    for ch in text:
        rows = glyph(ch)
        for r, row in enumerate(rows):
            c = 0
            while c < len(row):
                if row[c] == "#":
                    start = c
                    while c < len(row) and row[c] == "#":
                        c += 1
                    d.append(f"M{n(cx + start * s)} {n(y + r * s)}h{n((c - start) * s)}v{n(s)}h{n(-(c - start) * s)}z")
                else:
                    c += 1
        cx += (len(rows[0]) + 1) * s
    return "".join(d)


