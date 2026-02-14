# Teen Compute & Safety Monitor

AI agent that runs on the teenager's Mac to track compute usage and perform periodic screen monitoring with harmful-content flagging. A parent dashboard shows usage and alerts.

## Layout

- **agent/** – macOS agent (screen capture, usage tracker, harmful-content classifier)
- **backend/** – FastAPI server that receives events and serves the dashboard API
- **dashboard/** – Parent web UI (static HTML) to view usage and alerts

## Requirements

- macOS (for screen capture and frontmost-app detection)
- Python 3.10+
- OpenAI API key (for moderation + optional vision)

## Setup

### 1. Backend

```bash
cd /Users/TestAgent/code/backend
pip install -r requirements.txt
export BACKEND_API_KEY=your-secret-key
python main.py
# Or: uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Agent (on teen's machine)

```bash
cd /Users/TestAgent/code
pip install -r agent/requirements.txt
```

- Grant **Screen Recording** permission (System Settings → Privacy & Security).
- Optionally grant **Accessibility** for window titles (System Settings → Privacy & Security).

Edit `agent/config.yaml`:

- `backend.url`: backend URL (e.g. `http://localhost:8000` or your server)
- `backend.api_key`: same as `BACKEND_API_KEY` on the backend
- `device_id`: unique id for this device
- `classifier.openai_api_key` or set `OPENAI_API_KEY` in the environment

Run the agent:

```bash
cd /Users/TestAgent/code
export PYTHONPATH=/Users/TestAgent/code
python -m agent.agent
```

### 3. Parent dashboard

Open `dashboard/index.html` in a browser (or serve the folder with any static server). Set the API URL and API key (same as backend), then click Save and Refresh to see usage and alerts.

### 4. Run agent as a background service (LaunchAgent)

```bash
# Copy plist (adjust paths inside if needed)
cp com.cursor.teenmonitor.agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cursor.teenmonitor.agent.plist
```

To stop: `launchctl unload ~/Library/LaunchAgents/com.cursor.teenmonitor.agent.plist`

Logs: `/tmp/teenmonitor-agent.log` and `/tmp/teenmonitor-agent.err`.

## Config (agent/config.yaml)

- **capture.interval_seconds** – how often to take a screenshot (default 45)
- **capture.store_screenshot_on_alert** – whether to attach a redacted screenshot to alerts (default false)
- **classifier.enabled** – turn harmful-content detection on/off
- **classifier.alert_cooldown_seconds** – max one alert per category per N seconds (default 300)
- **usage** – toggles for time, active app, window title, CPU/memory

## Privacy

- Screenshots are processed in memory and discarded unless an alert is raised and `store_screenshot_on_alert` is true.
- Alerts send only category and metadata to the backend by default; no screenshot is stored unless you enable it and implement upload in the agent.
# buddyguard
