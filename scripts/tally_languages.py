#!/usr/bin/env python3
"""Tally language share across your repos (private included) into data/languages.json.

    python3 scripts/tally_languages.py

Runs on the Mac, not in Actions: the Actions token only sees public repos, and most
work lives in private ones. Uses your `gh` login. Only language percentages are
written; repo names never leave the machine.

Each repo counts equally (its language mix is normalized before averaging), so one
repo full of generated HTML can't drown out everything else.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "languages.json"
PROFILE = REPO / "data" / "profile.json"
TOP = 6

QUERY = """
{ viewer {
  repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
    nodes { nameWithOwner languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
  }
  repositoriesContributedTo(first: 100, includeUserRepositories: false, contributionTypes: [COMMIT, PULL_REQUEST]) {
    nodes { nameWithOwner languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
  }
} }"""


def repo_weighted_share(repos, exclude=(), top=TOP):
    """[(name, pct, color)], each repo contributing an equal share of the whole."""
    share, colors, counted = {}, {}, 0
    for repo in repos:
        edges = [e for e in repo["languages"]["edges"] if e["node"]["name"] not in exclude]
        size = sum(e["size"] for e in edges)
        if not size:
            continue
        counted += 1
        for e in edges:
            name = e["node"]["name"]
            share[name] = share.get(name, 0) + e["size"] / size
            colors[name] = e["node"].get("color") or "#a3a3a3"
    total = sum(share.values()) or 1
    ranked = sorted(share.items(), key=lambda kv: -kv[1])[:top]
    return [(name, round(v / total * 100, 2), colors[name]) for name, v in ranked], counted


def main():
    exclude = set(json.loads(PROFILE.read_text()).get("exclude_languages", []))
    try:
        raw = subprocess.run(["gh", "api", "graphql", "-f", f"query={QUERY}"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"gh api failed: {getattr(e, 'stderr', e)}")
    viewer = json.loads(raw)["data"]["viewer"]
    seen, repos = set(), []
    for key in ("repositories", "repositoriesContributedTo"):
        for r in viewer[key]["nodes"]:
            if r["nameWithOwner"] not in seen:
                seen.add(r["nameWithOwner"])
                repos.append(r)
    langs, counted = repo_weighted_share(repos, exclude)
    out = {"repos": counted, "languages": [{"name": n, "pct": p, "color": c} for n, p, c in langs]}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"{counted} repos: " + ", ".join(f"{n} {p:.1f}%" for n, p, _ in langs))


if __name__ == "__main__":
    main()
