#!/usr/bin/env bash
# Install Sonic Flights as a launchd user agent so it starts on login and
# restarts on crash. Postgres already autostarts via `brew services`.
set -euo pipefail

PLIST=com.sonicflights.app.plist
SRC="$(cd "$(dirname "$0")" && pwd)/$PLIST"
DEST="$HOME/Library/LaunchAgents/$PLIST"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$SRC" "$DEST"

# Reload if already loaded, then load.
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "Loaded $PLIST"
echo "Status:"
launchctl list | grep sonicflights || true
echo
echo "Manage with:"
echo "  launchctl unload $DEST   # stop + disable autostart"
echo "  launchctl load   $DEST   # start + enable autostart"
