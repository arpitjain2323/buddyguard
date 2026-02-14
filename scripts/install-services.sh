#!/usr/bin/env bash
# Install BuddyGuard backend and agent as LaunchAgents (production on teen's laptop).
# Run from the project root or from anywhere inside the repo.
# Optionally: export BACKEND_API_KEY=your-secret before running to bake it into the backend plist.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if git -C "$SCRIPT_DIR" rev-parse --show-toplevel &>/dev/null; then
  PROJECT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

BACKEND_PLIST="$PROJECT_ROOT/com.cursor.teenmonitor.backend.plist"
AGENT_PLIST="$PROJECT_ROOT/com.cursor.teenmonitor.agent.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

if [[ ! -f "$BACKEND_PLIST" ]] || [[ ! -f "$AGENT_PLIST" ]]; then
  echo "Expected plists at project root: com.cursor.teenmonitor.backend.plist, com.cursor.teenmonitor.agent.plist"
  exit 1
fi

# Ensure venv exists and has deps
VENV="$PROJECT_ROOT/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating venv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$PROJECT_ROOT/backend/requirements.txt" -r "$PROJECT_ROOT/agent/requirements.txt"
else
  echo "Using existing venv at $VENV"
fi

# Substitute __PROJECT_ROOT__ and optional __BACKEND_API_KEY__
API_KEY="${BACKEND_API_KEY:-REPLACE_ME}"
mkdir -p "$LAUNCH_AGENTS"

for name in backend agent; do
  src="$PROJECT_ROOT/com.cursor.teenmonitor.$name.plist"
  dest="$LAUNCH_AGENTS/com.cursor.teenmonitor.$name.plist"
  sed -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
      -e "s|__BACKEND_API_KEY__|$API_KEY|g" \
      < "$src" > "$dest"
  echo "Installed: $dest"
done

echo ""
echo "Next steps:"
echo "  1. If you did not set BACKEND_API_KEY, edit $LAUNCH_AGENTS/com.cursor.teenmonitor.backend.plist"
echo "     and replace REPLACE_ME in BACKEND_API_KEY with your secret. Use the same value in agent/config.yaml backend.api_key."
echo "  2. Edit agent/config.yaml: set device_id and backend.api_key to match the backend."
echo "  3. Load the services:"
echo "     launchctl load $LAUNCH_AGENTS/com.cursor.teenmonitor.backend.plist"
echo "     launchctl load $LAUNCH_AGENTS/com.cursor.teenmonitor.agent.plist"
echo "  4. To stop: launchctl unload ... (same paths with unload)."
echo "  Logs: /tmp/teenmonitor-backend.log and /tmp/teenmonitor-agent.log (and .err)."
