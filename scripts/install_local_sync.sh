#!/bin/bash
# Install (or remove) the launchd job that runs scripts/local_sync.py every 3 hours.
#
#   scripts/install_local_sync.sh            install / reinstall
#   scripts/install_local_sync.sh uninstall  remove the job and its clone
#
# launchd jobs can't read ~/Documents without Full Disk Access, so the job works
# in its own clone under ~/.local/share instead of this checkout.
set -euo pipefail

LABEL="com.scewmath.readme-card"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CLONE="$HOME/.local/share/scewmath-card/repo"
LOG="$HOME/Library/Logs/scewmath-card.log"
REMOTE="$(git -C "$(dirname "$0")/.." remote get-url origin)"

if [[ "${1:-}" == "uninstall" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  rm -rf "$(dirname "$CLONE")"
  echo "removed $LABEL (the token ledger in ~/Library/Application Support/scewmath-card is kept)"
  exit 0
fi

PYTHON="$(command -v python3)"
GIT_DIR="$(dirname "$(command -v git)")"
GH_DIR="$(dirname "$(command -v gh)")"

if [[ -d "$CLONE/.git" ]]; then
  git -C "$CLONE" pull --rebase --quiet
else
  mkdir -p "$(dirname "$CLONE")"
  git clone --quiet "$REMOTE" "$CLONE"
fi

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$CLONE/scripts/local_sync.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$GH_DIR:$GIT_DIR:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>10800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL: runs every 3h, logs at $LOG"
