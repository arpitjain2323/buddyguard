#!/usr/bin/env bash
# Recreate the venv for the current machine's native architecture (fixes PIL "incompatible architecture" when the app was running under Rosetta).
# Run from the project root: bash scripts/recreate-venv-native.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$PROJECT_ROOT/venv"
ARCH="$(uname -m)"

echo "Recreating venv at $VENV for $ARCH ..."
rm -rf "$VENV"
if [[ "$ARCH" = "arm64" ]]; then
  arch -arm64 python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$PROJECT_ROOT/backend/requirements.txt" -r "$PROJECT_ROOT/agent/requirements.txt"
else
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$PROJECT_ROOT/backend/requirements.txt" -r "$PROJECT_ROOT/agent/requirements.txt"
fi
echo "Done. Start the agent again (e.g. open BuddyGuardAgent.app or launchctl load the agent plist)."
