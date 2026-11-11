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


# ---------------------------------------------------------------- drawing
class Ctx:
    def __init__(self, accent, motion):
        self.accent = accent
        self.accent2 = tint(accent, 0.45)
        self.motion = motion


def divider(y, x1=0, x2=W):
    return f'<line x1="{n(x1)}" y1="{n(y)}" x2="{n(x2)}" y2="{n(y)}" stroke="{BORDER}" stroke-dasharray="4 4"/>'


def vdivider(x, y1, y2):
    return f'<line x1="{n(x)}" y1="{n(y1)}" x2="{n(x)}" y2="{n(y2)}" stroke="{BORDER}" stroke-dasharray="4 4"/>'


def heading(x, y, label, extra, ctx):
    tail = span(f"  ·  {extra}", DIM) if extra else ""
    return T(x, y, span(label.upper(), INK) + tail, size=12, extra=' letter-spacing="1.5"')


def grow_x(width, delay, ctx, dur=1.0):
    if not ctx.motion:
        return ""
    return (f'<animate attributeName="width" from="0" to="{n(width)}" dur="{dur}s" begin="{delay}s" '
            f'fill="freeze" calcMode="spline" keyTimes="0;1" keySplines=".2 .8 .2 1"/>')


def bar(x, y, w, h, frac, ctx, delay=0.0, segments=None):
    """Track + accent fill + dithered leading edge. segments: [(frac, color)] stacked."""
    out = [f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" fill="{TRACK}"/>']
    for i in range(1, 10):
        tx = x + w * i / 10
        out.append(f'<rect x="{n(tx)}" y="{n(y + h - 3)}" width="1" height="3" fill="{FAINT}"/>')
    segments = segments or [(frac, ctx.accent)]
    fill_w = max(min(sum(f for f, _ in segments), 1), 0) * w
    if fill_w <= 0:
        return "".join(out)
    cid = f"cl{abs(hash((x, y, w))) % 10**8}"
    out.append(f'<clipPath id="{cid}"><rect x="{n(x)}" y="{n(y)}" width="{n(fill_w)}" height="{n(h)}">'
               f'{grow_x(fill_w, delay, ctx)}</rect></clipPath>')
    inner, sx = [], x
    for f, color in segments:
        sw = max(min(f, 1), 0) * w
        inner.append(f'<rect x="{n(sx)}" y="{n(y)}" width="{n(sw)}" height="{n(h)}" fill="{color}"/>')
        sx += sw
    # dithered edge: checkerboard bleeding past the fill, like a cooling pixel trail
    edge = min(8, fill_w)
    inner.append(f'<rect x="{n(x + fill_w - edge)}" y="{n(y)}" width="{n(edge)}" height="{n(h)}" fill="url(#dither)"/>')
    out.append(f'<g clip-path="url(#{cid})">{"".join(inner)}</g>')
    out.append(f'<rect x="{n(x + fill_w)}" y="{n(y)}" width="4" height="{n(h)}" fill="url(#dither)" opacity=".6"/>')
    return "".join(out)


def big_number(text, x, y, s, ctx):
    """Pixel digits with a dithered drop shadow."""
    off = max(s / 2, 1.5)
    return (f'<path d="{px_path(text, x + off, y + off, s)}" fill="url(#shade)"/>'
            f'<path d="{px_path(text, x, y, s)}" fill="{INK}"/>')


def defs(ctx):
    return (
        "<defs>"
        f'<pattern id="dither" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="2" height="2" fill="{ctx.accent}"/><rect x="2" y="2" width="2" height="2" fill="{ctx.accent}"/></pattern>'
        f'<pattern id="shade" width="2" height="2" patternUnits="userSpaceOnUse">'
        f'<rect width="1" height="1" fill="#4a4a4a"/><rect x="1" y="1" width="1" height="1" fill="#4a4a4a"/></pattern>'
        "</defs>"
    )


def blink(ctx, dur="1.1s"):
    if not ctx.motion:
        return ""
    return f'<animate attributeName="opacity" values="1;0" keyTimes="0;.5" calcMode="discrete" dur="{dur}" repeatCount="indefinite"/>'


# ---------------------------------------------------------------- sections
def sec_topbar(ctx, d, profile):
    login = profile["login"]
    loc = profile.get("location", "").split(",")[0].strip().replace(" ", "-") or "home"
    prompt = span(login, ctx.accent, 600) + span(f"@{loc}", MID) + span(":~$ ", DIM) + span("./readme --live", INK)
    out = [
        T(P, 28, prompt, size=13),
        T(W - P, 28, esc(f"github.com/{login}"), size=12, fill=DIM, anchor="end"),
    ]
    return "".join(out), 44


def sec_header(ctx, d, profile):
    s = 8
    name = profile["name"]
    y = 34
    wname = px_width(name, s)
    out = [
        f'<path d="{px_path(name, P + 4, y + 4, s)}" fill="{ctx.accent}"/>',
        f'<path d="{px_path(name, P, y, s)}" fill="{INK}"/>',
        f'<rect x="{n(P + wname + 2 * s)}" y="{n(y)}" width="{n(4 * s)}" height="{n(7 * s + 4)}" fill="{ctx.accent}">{blink(ctx)}</rect>',
    ]
    tag = profile.get("tagline", "")
    ty = y + 7 * s + 42
    text = T(P, ty, span("> ", ctx.accent, 700) + span(tag, INK), size=17)
    if ctx.motion and tag:
        # typewriter: reveal one character per step
        full = cw(17) * (len(tag) + 2) + 4
        steps = len(tag) + 2
        values = ";".join(n(full * i / steps) for i in range(steps + 1))
        out.append(
            f'<clipPath id="type"><rect x="{P}" y="{n(ty - 20)}" width="{n(full)}" height="28">'
            f'<animate attributeName="width" values="{values}" dur="{steps * 0.07:.2f}s" begin=".4s" '
            f'calcMode="discrete" fill="freeze"/></rect></clipPath>'
            f'<g clip-path="url(#type)">{text}</g>'
        )
    else:
        out.append(text)
    return "".join(out), ty + 26


def icon_markup(item, icons, x, y, size):
    name = item["name"]
    if "mono" in item:
        label = item["mono"]
        s = 1.25
        tw, th = px_width(label, s), 7 * s
        return (f'<rect x="{n(x)}" y="{n(y)}" width="{size}" height="{size}" rx="5" fill="{item.get("color", MID)}"/>'
                f'<path d="{px_path(label, x + (size - tw) / 2, y + (size - th) / 2, s)}" fill="#fff"/>')
    ic = icons.get(name)
    if not ic:
        return ""
    return f'<svg x="{n(x)}" y="{n(y)}" width="{size}" height="{size}" viewBox="{ic["viewBox"]}">{ic["body"]}</svg>'


def sec_stack(ctx, d, profile, stack, icons):
    total = sum(len(g["items"]) for g in stack)
    out = [heading(P, 34, "stack", f"{total} tools", ctx)]
    size, step, row_h = 28, 46, 46
    y0 = 58
    for r, group in enumerate(stack):
        ry = y0 + r * row_h
        out.append(T(P, ry + size / 2 + 4, esc(group["group"]), size=12, fill=DIM))
        out.append(f'<rect x="{P + 120}" y="{n(ry + size / 2)}" width="12" height="1" fill="{FAINT}"/>')
        for i, item in enumerate(group["items"]):
            ix = P + 150 + i * step
            g = icon_markup(item, icons, ix, ry, size)
            if ctx.motion:
                delay = 0.15 + r * 0.12 + i * 0.04
                g = (f'<g opacity="0">{g}<animate attributeName="opacity" from="0" to="1" dur=".35s" '
                     f'begin="{delay:.2f}s" fill="freeze"/></g>')
            out.append(g)
    return "".join(out), y0 + len(stack) * row_h + 4


def sec_activity(ctx, d, profile):
    out = []
    window = d["window"]
    recent = sum(c for _, c in window)
    out.append(heading(P, 34, "contributions", f"{fmt(recent)} in the last 30 days", ctx))
    cx, cy, cwid, ch = P, 64, SPLIT - P - 28, 128
    base = cy + ch
    peak = max((c for _, c in window), default=0) or 1
    slot = cwid / len(window)
    bw = max(slot - 4, 2)
    peak_i = max(range(len(window)), key=lambda i: window[i][1])
    for i, (day, c) in enumerate(window):
        bx = cx + i * slot + (slot - bw) / 2
        if c == 0:
            out.append(f'<rect x="{n(bx)}" y="{n(base - 2)}" width="{n(bw)}" height="2" fill="{FAINT}"/>')
            continue
        bh = max(c / peak * ch, 3)
        color = ctx.accent if i == len(window) - 1 or c >= peak * 0.5 else tint(ctx.accent, 0.0)
        opacity = "" if c >= peak * 0.5 else ' opacity=".55"'
        anim = ""
        if ctx.motion:
            dl = 0.2 + i * 0.025
            anim = (f'<animate attributeName="height" from="0" to="{n(bh)}" dur=".6s" begin="{dl:.3f}s" fill="freeze" '
                    f'calcMode="spline" keyTimes="0;1" keySplines=".2 .8 .2 1"/>'
                    f'<animate attributeName="y" from="{n(base)}" to="{n(base - bh)}" dur=".6s" begin="{dl:.3f}s" fill="freeze" '
                    f'calcMode="spline" keyTimes="0;1" keySplines=".2 .8 .2 1"/>')
        out.append(f'<rect x="{n(bx)}" y="{n(base - bh)}" width="{n(bw)}" height="{n(bh)}" fill="{color}"{opacity}>{anim}</rect>')
    if window[peak_i][1] > 0:
        px = cx + peak_i * slot + slot / 2
        out.append(T(px, base - ch - 8, fmt(window[peak_i][1]), size=11, fill=MID, anchor="middle"))
    out.append(f'<line x1="{n(cx)}" y1="{n(base + 6)}" x2="{n(cx + cwid)}" y2="{n(base + 6)}" stroke="{FAINT}" stroke-dasharray="3 3"/>')
    out.append(T(cx, base + 26, month_day(window[0][0]), size=12, fill=DIM))
    out.append(T(cx + cwid, base + 26, "today", size=12, fill=DIM, anchor="end"))

    # totals column
    rx = SPLIT + 24
    out.append(heading(rx, 34, "totals", "all time", ctx))
    cur, best = d["streak"]
    rows = [(fmt(d["total"]), "contributions"), (str(cur), "day streak, now"), (str(best), "day streak, best")]
    s = 4
    numw = max(px_width(v, s) for v, _ in rows)
    for i, (v, label) in enumerate(rows):
        ry = 58 + i * 42
        out.append(big_number(v, rx, ry, s, ctx))
        out.append(T(rx + numw + 18, ry + 22, esc(label), size=13, fill=MID))
    by = 58 + 3 * 42 + 6
    bw2 = W - P - rx - 64
    out.append(bar(rx, by, bw2, 12, cur / best if best else 0, ctx, delay=0.6))
    out.append(T(W - P, by + 11, f"{cur}/{best}", size=13, fill=INK, anchor="end"))
    h = base + 42
    out.append(vdivider(SPLIT, 0, h))
    return "".join(out), h


