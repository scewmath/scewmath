#!/usr/bin/env python3
"""Download the stack logos listed in data/stack.json into data/icons.json.

Run this by hand whenever you add or change a tool in data/stack.json:

    python3 scripts/vendor_icons.py

Logos come from Devicon (MIT) or Simple Icons (CC0). They are cleaned up so they
embed safely in one SVG: ids get a unique prefix, scripts and event handlers are
dropped, and near-black fills are lightened so they show on the dark card.
Items with "mono" get no download; build_card.py draws a pixel monogram tile.
"""

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "data" / "stack.json"
OUT = ROOT / "data" / "icons.json"

DEVICON = "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/{}.svg"
SIMPLE = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{}.svg"
SIMPLE_DATA = "https://cdn.jsdelivr.net/npm/simple-icons@latest/data/simple-icons.json"
LIGHT = "#ededed"
SVG_NS = "http://www.w3.org/2000/svg"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "scewmath-readme-card"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def luminance(hex_color):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def lighten_dark(text):
    """Swap near-black colors for light ink so logos survive a dark background."""
    def swap(m):
        return LIGHT if luminance(m.group(0)) < 0.18 else m.group(0)
    return re.sub(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", swap, text)


def clean(svg_text, prefix, default_fill=None):
    """Return (viewBox, inner markup) with ids namespaced and dark fills lightened."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(svg_text)
    view_box = root.get("viewBox") or f"0 0 {root.get('width', 128)} {root.get('height', 128)}"

    for parent in root.iter():
        for child in list(parent):
            tag = child.tag.split("}")[-1]
            if tag in ("script", "title", "desc", "metadata", "foreignObject"):
                parent.remove(child)
        for attr in list(parent.attrib):
            if attr.lower().startswith("on"):
                del parent.attrib[attr]

    inner = "".join(ET.tostring(c, encoding="unicode") for c in root)
    inner = re.sub(r"\sxmlns(:\w+)?=\"[^\"]*\"", "", inner)
    inner = re.sub(r"\b(ns\d+|svg):", "", inner)

    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    for i in sorted(ids, key=len, reverse=True):
        new = f"{prefix}-{i}"
        inner = inner.replace(f'id="{i}"', f'id="{new}"')
        inner = inner.replace(f"url(#{i})", f"url(#{new})")
        inner = inner.replace(f'href="#{i}"', f'href="#{new}"')

    inner = lighten_dark(inner)
    # Children without a fill inherit black by default; give them light ink instead.
    fill = root.get("fill") or default_fill or LIGHT
    fill = lighten_dark(fill) if fill.startswith("#") else fill
    return view_box, f'<g fill="{fill}">{inner}</g>'


def main():
    stack = json.loads(STACK.read_text())
    simple_hex = None
    icons = {}
    n = 0
    for group in stack:
        for item in group["items"]:
            name = item["name"]
            prefix = f"ic{n}"
            n += 1
            if "mono" in item:
                continue
            if "devicon" in item:
                vb, body = clean(get(DEVICON.format(item["devicon"])), prefix)
            elif "simpleicons" in item:
                if simple_hex is None:
                    data = json.loads(get(SIMPLE_DATA))
                    data = data["icons"] if isinstance(data, dict) else data
                    simple_hex = {
                        (i.get("slug") or re.sub(r"[^a-z0-9]", "", i["title"].lower())): i["hex"]
                        for i in data
                    }
                slug = item["simpleicons"]
                vb, body = clean(get(SIMPLE.format(slug)), prefix, "#" + simple_hex.get(slug, "ededed"))
            else:
                print(f"skip {name}: no source", file=sys.stderr)
                continue
            icons[name] = {"viewBox": vb, "body": body}
            print(f"ok   {name}")
    OUT.write_text(json.dumps(icons, indent=1) + "\n")
    print(f"wrote {len(icons)} icons to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
