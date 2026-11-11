#!/usr/bin/env python3
"""Tally AI token usage on this Mac and write data/tokens.json.

    python3 scripts/tally_tokens.py

(scripts/local_sync.py runs this and pushes the result.)

Sources:
  Claude Code  ~/.claude/projects/**/*.jsonl   assistant messages carry message.usage;
               streaming writes the same message id several times, so we keep the
               max per id.
  Codex        ~/.codex/{sessions,archived_sessions}/**/rollout-*.jsonl  token_count
               events carry a running total per session; we keep the max.

Both tools prune old logs, so every message/session seen is recorded in a ledger
outside the repo (~/Library/Application Support/scewmath-card/ledger.json). The
total only ever grows. Only the aggregate numbers are published.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
LEDGER = Path(os.environ.get("TOKEN_LEDGER", HOME / "Library/Application Support/scewmath-card/ledger.json"))
CLAUDE_DIR = Path(os.environ.get("CLAUDE_LOG_DIR", HOME / ".claude/projects"))
CODEX_DIRS = [HOME / ".codex/sessions", HOME / ".codex/archived_sessions"]


def claude_records(paths):
    """Yield (key, total, fresh, day) for each Claude Code API message."""
    for path in paths:
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                    continue
                u = msg["usage"]
                inp = u.get("input_tokens") or 0
                out = u.get("output_tokens") or 0
                write = u.get("cache_creation_input_tokens") or 0
                read = u.get("cache_read_input_tokens") or 0
                total = inp + out + write + read
                if not total:
                    continue
                key = msg.get("id") or rec.get("requestId") or rec.get("uuid")
                if not key:
                    continue
                yield key, total, inp + out + write, (rec.get("timestamp") or "")[:10]


def codex_records(paths):
    """Yield (session_key, total, fresh, day) using each session's final running total."""
    for path in paths:
        best = None
        day = ""
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"token_count"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                info = (rec.get("payload") or {}).get("info") or {}
                u = info.get("total_token_usage")
                if not u:
                    continue
                total = u.get("total_tokens") or 0
                if best is None or total > best[0]:
                    fresh = (u.get("input_tokens") or 0) - (u.get("cached_input_tokens") or 0) + (u.get("output_tokens") or 0)
                    best = (total, fresh)
                    day = day or (rec.get("timestamp") or "")[:10]
        if best and best[0]:
            yield path.stem, best[0], best[1], day


def merge(ledger_part, records):
    """Fold records into {key: [total, fresh, day]}, keeping the max total per key."""
    for key, total, fresh, day in records:
        old = ledger_part.get(key)
        if old is None:
            ledger_part[key] = [total, fresh, day]
        elif total > old[0]:
            ledger_part[key] = [total, fresh, old[2] or day]


def summarize(ledger, now):
    by_tool = {}
    days = []
    for tool in ("claude_code", "codex"):
        part = ledger.get(tool, {})
        by_tool[tool] = {
            "total": sum(v[0] for v in part.values()),
            "fresh": sum(v[1] for v in part.values()),
        }
        days += [v[2] for v in part.values() if v[2]]
    return {
        "total": sum(t["total"] for t in by_tool.values()),
        "fresh": sum(t["fresh"] for t in by_tool.values()),
        "by_tool": by_tool,
        "since": min(days) if days else now.date().isoformat(),
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def load_ledger():
    try:
        return json.loads(LEDGER.read_text())
    except (OSError, json.JSONDecodeError):
        return {"claude_code": {}, "codex": {}}


def save_ledger(ledger):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, separators=(",", ":")))
    tmp.replace(LEDGER)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "data" / "tokens.json")
    args = ap.parse_args(argv)

    ledger = load_ledger()
    ledger.setdefault("claude_code", {})
    ledger.setdefault("codex", {})
    merge(ledger["claude_code"], claude_records(sorted(CLAUDE_DIR.rglob("*.jsonl"))))
    merge(ledger["codex"], codex_records(sorted(p for d in CODEX_DIRS if d.exists() for p in d.rglob("rollout-*.jsonl"))))
    save_ledger(ledger)

    summary = summarize(ledger, datetime.now(timezone.utc))
    old = {}
    if args.out.exists():
        old = json.loads(args.out.read_text())
    # Only bump the file when the numbers move, so idle runs don't create commits.
    if {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in summary.items() if k != "updated"}:
        print(f"no change: {summary['total']:,} tokens")
    else:
        args.out.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{summary['total']:,} tokens "
              f"(claude code {summary['by_tool']['claude_code']['total']:,}, codex {summary['by_tool']['codex']['total']:,})")


if __name__ == "__main__":
    sys.exit(main())
