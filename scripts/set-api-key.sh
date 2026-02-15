#!/usr/bin/env bash
# Set BACKEND_API_KEY in the installed backend LaunchAgent and restart the backend.
# Also reminds you to set the same key in agent/config.yaml and in the dashboard.
# Usage: bash scripts/set-api-key.sh "your-secret-key"
# (Key must not contain double quotes.)

set -e

KEY="${1:?Usage: $0 <api-key>}"
PLIST="$HOME/Library/LaunchAgents/com.cursor.teenmonitor.backend.plist"

if [[ ! -f "$PLIST" ]]; then
  echo "Backend plist not found at $PLIST"
  echo "Run: bash scripts/install-services.sh"
  exit 1
fi

/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:BACKEND_API_KEY \"$KEY\"" "$PLIST"
echo "Set BACKEND_API_KEY in backend plist."

echo "Restarting backend so it picks up the new key..."
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Backend restarted."

echo ""
echo "Next: use the SAME key in agent/config.yaml (backend.api_key) and in the dashboard."
echo "Then restart the agent: pkill -f agent.agent; open ~/buddyguard/BuddyGuardAgent.app"
