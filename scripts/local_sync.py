#!/usr/bin/env python3
"""The Mac half of the card: tally tokens + languages, then push if anything changed.

    python3 scripts/local_sync.py            # tally and push
    python3 scripts/local_sync.py --no-push  # tally only

launchd runs this every 3 hours (see scripts/install_local_sync.sh). A push to
data/ triggers the GitHub Action, which redraws the card right away.
"""

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FILES = ["data/tokens.json", "data/languages.json"]


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(REPO), *args], check=check, capture_output=True, text=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args(argv)

    if not args.no_push:
        git("pull", "--rebase", "--autostash", "--quiet")
    for script in ("tally_tokens.py", "tally_languages.py"):
        subprocess.run([sys.executable, str(HERE / script)], check=True)
    if args.no_push:
        return
    git("add", *FILES)
    if git("diff", "--staged", "--quiet", check=False).returncode == 0:
        print("nothing changed")
        return
    git("commit", "--quiet", "-m", "Sync token spend and languages")
    git("push", "--quiet")
    print("pushed")


if __name__ == "__main__":
    main()
