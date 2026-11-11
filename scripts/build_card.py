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


# ---------------------------------------------------------------- helpers
def n(v):
    v = round(float(v), 2)
    return str(int(v)) if v.is_integer() else str(v)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def cw(size):
    """Approximate advance width of one monospace character."""
    return size * 0.602


def clip(text, size, max_w):
    max_chars = int(max_w / cw(size))
    return text if len(text) <= max_chars else text[: max(max_chars - 1, 1)] + "…"


def T(x, y, text, size=13, fill=INK, anchor="start", weight=400, extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight != 400 else ""
    return f'<text x="{n(x)}" y="{n(y)}" font-size="{size}" fill="{fill}"{a}{w}{extra}>{text}</text>'


def span(text, fill, weight=400):
    w = f' font-weight="{weight}"' if weight != 400 else ""
    return f'<tspan fill="{fill}"{w}>{esc(text)}</tspan>'


def fmt(v):
    return f"{int(v):,}"


def short(v):
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div:
            x = v / div
            return (f"{x:.0f}" if x >= 100 else f"{x:.1f}".rstrip("0").rstrip(".")) + suf
    return str(int(v))


def human(v):
    for div, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if v >= div:
            return f"{v / div:.2f} {word}"
    return fmt(v)


def milestone(v):
    """Next round goal above v: 1, 2, 5 x 10^k."""
    k = 1
    while True:
        for m in (1, 2, 5):
            if m * k > v:
                return m * k
        k *= 10


def tint(hex_color, amount):
    """Mix a color toward white by amount (0..1)."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in rgb)


def month_day(d):
    return f"{d.strftime('%b').lower()} {d.day}"


def month_year(d):
    return f"{d.strftime('%b').lower()} {d.year}"


# ---------------------------------------------------------------- pure stats
def compute_streaks(days, today):
    """days: {date: count}. Returns (current, best).

    Today counts toward the current streak if it has contributions, but an empty
    today doesn't break it: the day isn't over yet.
    """
    best = run = 0
    d = min(days) if days else today
    while d <= today:
        if days.get(d, 0) > 0:
            run += 1
            best = max(best, run)
        else:
            run = 0
        d += timedelta(days=1)
    cur = 0
    d = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    while days.get(d, 0) > 0:
        cur += 1
        d -= timedelta(days=1)
    return cur, best


def aggregate_languages(repos, exclude=(), top=6):
    sizes, colors = {}, {}
    for repo in repos:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            if name in exclude:
                continue
            sizes[name] = sizes.get(name, 0) + edge["size"]
            colors[name] = edge["node"].get("color") or MID
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])[:top]
    return [(name, size / total * 100, colors[name]) for name, size in ranked]


# ---------------------------------------------------------------- github
def github_token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("No GITHUB_TOKEN and `gh auth token` failed.")


def graphql(query, variables, token):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": "scewmath-readme-card"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


PROFILE_Q = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection { contributionYears }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository {
        nameWithOwner name description stargazerCount pushedAt
        primaryLanguage { name color }
      } }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
        edges { size node { name color } }
      } }
    }
  }
}"""


def fetch_calendar(login, years, token):
    parts = [
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") '
        "{ contributionCalendar { weeks { contributionDays { date contributionCount } } } }"
        for y in years
    ]
    q = "query($login: String!) { user(login: $login) { " + " ".join(parts) + " } }"
    user = graphql(q, {"login": login}, token)["user"]
    days = {}
    for coll in user.values():
        for week in coll["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[date.fromisoformat(day["date"])] = day["contributionCount"]
    return days


def build_data(profile, now=None):
    token = github_token()
    login = profile["login"]
    tz = ZoneInfo(profile.get("timezone", "UTC"))
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(tz).date()

    user = graphql(PROFILE_Q, {"login": login}, token)["user"]
    days = fetch_calendar(login, user["contributionsCollection"]["contributionYears"], token)
    days = {d: c for d, c in days.items() if d <= today}
    cur, best = compute_streaks(days, today)
    window = [(today - timedelta(days=i), days.get(today - timedelta(days=i), 0)) for i in range(29, -1, -1)]

    overrides = profile.get("project_overrides", {})
    pinned = []
    for node in user["pinnedItems"]["nodes"]:
        o = overrides.get(node["nameWithOwner"], {})
        lang = node.get("primaryLanguage") or {}
        pinned.append({
            "nwo": node["nameWithOwner"],
            "name": o.get("name", node["name"].lower()),
            "badge": o.get("badge"),
            "blurb": o.get("blurb") or (node.get("description") or "").lower(),
            "lang": (lang.get("name") or "").lower(),
            "lang_color": lang.get("color") or MID,
            "stars": node["stargazerCount"],
            "pushed": datetime.fromisoformat(node["pushedAt"].replace("Z", "+00:00")).date(),
        })

    tokens_path = DATA / "tokens.json"
    langs_path = DATA / "languages.json"
    if langs_path.exists():
        langs_doc = json.loads(langs_path.read_text())
        langs = [(l["name"], l["pct"], l["color"]) for l in langs_doc["languages"]]
        langs_note = f"{langs_doc['repos']} repos, each weighted equally"
    else:
        langs = aggregate_languages(user["repositories"]["nodes"], set(profile.get("exclude_languages", [])))
        langs_note = "by bytes, public repos"
    return {
        "now": now,
        "today": today,
        "window": window,
        "total": sum(days.values()),
        "streak": (cur, best),
        "langs": langs,
        "langs_note": langs_note,
        "pinned": pinned,
        "tokens": json.loads(tokens_path.read_text()) if tokens_path.exists() else None,
    }


