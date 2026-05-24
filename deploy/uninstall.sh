#!/usr/bin/env bash
set -euo pipefail
LABEL="com.kengyit.claude-storyteller"
UID_VAL=$(id -u)
launchctl bootout "gui/$UID_VAL/$LABEL" || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "[uninstall] removed $LABEL"
