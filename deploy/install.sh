#!/usr/bin/env bash
# Installs claude-storyteller as a per-user LaunchAgent on macOS.
# Idempotent: re-running re-renders the plist and reloads the agent.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.kengyit.claude-storyteller"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCH_AGENTS_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
ENV_FILE_DEFAULT="$HOME/.config/claude-storyteller/.env"
ENV_FILE="${CLAUDE_STORYTELLER_ENV:-$ENV_FILE_DEFAULT}"

echo "[install] app dir   : $APP_DIR"
echo "[install] env file  : $ENV_FILE"
echo "[install] plist dest: $PLIST_DEST"

if [ ! -f "$ENV_FILE" ]; then
  echo "[install] WARNING: env file not found at $ENV_FILE"
  echo "          Copy .env.example to that path and fill it in before starting."
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[install] ERROR: 'uv' is required. Install with:"
  echo "          curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

echo "[install] syncing Python dependencies via uv..."
( cd "$APP_DIR" && uv sync )

UID_VAL=$(id -u)

# Render the plist template by replacing placeholders.
sed \
  -e "s|__APP_DIR__|${APP_DIR}|g" \
  -e "s|__ENV_FILE__|${ENV_FILE}|g" \
  -e "s|__LOG_DIR__|${LOG_DIR}|g" \
  "$APP_DIR/deploy/$LABEL.plist" > "$PLIST_DEST"

# Reload: bootout (if loaded) then bootstrap.
if launchctl print "gui/$UID_VAL/$LABEL" >/dev/null 2>&1; then
  echo "[install] bootout existing service..."
  launchctl bootout "gui/$UID_VAL/$LABEL" || true
fi

echo "[install] bootstrap..."
launchctl bootstrap "gui/$UID_VAL" "$PLIST_DEST"
launchctl enable "gui/$UID_VAL/$LABEL"
launchctl kickstart -k "gui/$UID_VAL/$LABEL"

echo "[install] done. Tail logs with:"
echo "  tail -f $LOG_DIR/claude-storyteller.out.log $LOG_DIR/claude-storyteller.err.log"
echo "[install] check status with:"
echo "  launchctl print gui/$UID_VAL/$LABEL | head"
