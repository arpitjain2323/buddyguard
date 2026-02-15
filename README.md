# Teen Compute & Safety Monitor

AI agent that runs on the teenager's Mac to track compute usage and perform periodic screen monitoring with harmful-content flagging. A parent dashboard shows usage and alerts.

## Layout

- **agent/** – macOS agent (screen capture, usage tracker, harmful-content classifier)
- **backend/** – FastAPI server that receives events and serves the dashboard API
- **dashboard/** – Parent web UI (static HTML) to view usage and alerts

## Quick start: same WiFi (teen + parent on one network)

BuddyGuard runs on the **teen's Mac**; the **parent** only needs a browser. Repo: **https://github.com/arpitjain2323/buddyguard**

### On the teenager's Mac (one-time setup)

1. **Clone the repo and go into it:**
   ```bash
   git clone https://github.com/arpitjain2323/buddyguard.git
   cd buddyguard
   ```

2. **Create a virtualenv and install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r backend/requirements.txt -r agent/requirements.txt
   ```

3. **Pick a shared API key** (e.g. a passphrase only you and the parent know). You'll use it in the next steps.

4. **Grant permissions (important for LaunchAgents):**  
   When the agent runs as a LaunchAgent, **launchd** starts Python directly — your terminal is not running. Adding only the terminal to Screen Recording is **not enough**; you’ll get desktop/screensaver only. The process that must have Screen Recording is the **venv Python** binary.  
   **If you can’t add python3 via the “+” button** (macOS often only lets you pick .app bundles), do this instead:  
   - Open **Terminal** (or iTerm2).  
   - Run the agent **once** using the **full path** to the venv Python, e.g.:  
     `~/buddyguard/venv/bin/python -m agent.agent`  
     (replace `~/buddyguard` with your project path if different).  
   - Wait for the first screen capture (about 1 minute, or whatever `capture.interval_seconds` is in `agent/config.yaml`).  
   - When macOS shows **“python3” (or “Python”) wants to record the screen”**, click **OK** / **Allow**. That adds the Python binary to Screen Recording.  
   - Stop the agent with **Ctrl+C**, then start it via LaunchAgent as in step 6. The same Python will now have permission when launchd runs it.  
   **If you can add it manually:** System Settings → Privacy & Security → Screen Recording → **+** → press **Cmd+Shift+G** and go to `~/buddyguard/venv/bin` → if **python3** (or **python**) is listed and selectable, choose it and Open; enable it. Then unload and load the agent again.  
   Optionally **Accessibility** for better window titles.

5. **Edit `agent/config.yaml`:**
   - Set `device_id` to a name for this laptop (e.g. `teen-laptop`).
   - Set `backend.api_key` to the shared API key from step 3.
   - Leave `backend.url` as `http://localhost:8000`.

6. **Install and start the services:**
   ```bash
   export BACKEND_API_KEY=your-shared-api-key   # same as in config.yaml
   bash scripts/install-services.sh
   launchctl load ~/Library/LaunchAgents/com.cursor.teenmonitor.backend.plist
   launchctl load ~/Library/LaunchAgents/com.cursor.teenmonitor.agent.plist
   ```
   If you didn't set `BACKEND_API_KEY` above, open `~/Library/LaunchAgents/com.cursor.teenmonitor.backend.plist` in a text editor and replace `REPLACE_ME` in the `BACKEND_API_KEY` value with your shared key.

7. **Find this laptop's IP address** (parent will need it):  
   **System Settings → Network → Wi-Fi → Details** (or your connection). Note the IP (e.g. `192.168.1.105`). Share this and the shared API key with the parent.

Done. Backend and agent start at login and keep running. Logs: `/tmp/teenmonitor-backend.log`, `/tmp/teenmonitor-agent.log` (and `.err`).

### On the parent's Mac (no install)

1. **Get from the teen:** the teen laptop's IP (e.g. `192.168.1.105`) and the **shared API key**.

2. **Open a browser** and go to:  
   **http://&lt;teen-laptop-ip&gt;:8000**  
   Example: `http://192.168.1.105:8000`

3. **In the dashboard:** enter the API key, click **Save**, then **Refresh** to see usage and alerts.

4. If the page doesn't load, the teen's Mac firewall may be blocking it: on the **teen's** Mac, **System Settings → Network → Firewall** and allow the connection when prompted, or allow Python.

**"Failed to fetch" or usage summary won't load:**  
- Confirm **API URL** matches how you opened the dashboard: if you're on the parent's device, it must be `http://<teen-laptop-ip>:8000` (no trailing slash). If you opened the dashboard at `http://192.168.1.105:8000`, leave API URL as that (or leave blank — the dashboard can default to the current host).  
- Backend must be running on the teen's Mac (`launchctl list | grep teenmonitor` should show both services).  
- Same WiFi; firewall on the teen's Mac may need to allow Python/incoming connections.

**Screenshots show only desktop/screensaver (or menu bar + desktop):**  
- The process that captures is **Python** (venv), not your terminal. If you can’t add python3 via the “+” button in Screen Recording, use the **run-once-from-Terminal** workaround in step 4 above: run `~/buddyguard/venv/bin/python -m agent.agent` from Terminal, allow the macOS prompt when it appears, then stop and use LaunchAgent again.

---

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

## Production setup on the teen's laptop

Run backend and agent automatically at login so the stack keeps running after reboot. Parent can open the dashboard from the same laptop or from another device on the same Wi‑Fi.

### One-time setup

1. **Clone or copy the repo** to the teen's Mac (e.g. `~/buddyguard`).

2. **Create a venv and install dependencies:**
   ```bash
   cd ~/buddyguard
   python3 -m venv venv
   source venv/bin/activate
   pip install -r backend/requirements.txt -r agent/requirements.txt
   ```

3. **Choose a shared API key** (e.g. a passphrase). You will set it in the backend plist and in `agent/config.yaml` as `backend.api_key`.

4. **Grant permissions:** System Settings → Privacy & Security → **Screen Recording** (required). Run the agent once from Terminal so macOS prompts for Screen Recording; grant it so captures show the frontmost window instead of only the desktop. Optionally **Accessibility** for window titles.

5. **Edit `agent/config.yaml`:** Set `device_id` (e.g. `teen-laptop`) and `backend.api_key` to the same secret as the backend.

6. **Install the LaunchAgents** (backend + agent) with the install script:
   ```bash
   cd ~/buddyguard
   export BACKEND_API_KEY=your-secret-key   # optional: bakes into plist
   bash scripts/install-services.sh
   ```
   If you did not set `BACKEND_API_KEY` above, edit `~/Library/LaunchAgents/com.cursor.teenmonitor.backend.plist` and replace `REPLACE_ME` in the `BACKEND_API_KEY` environment value with your secret.

7. **Load the services:**
   ```bash
   launchctl load ~/Library/LaunchAgents/com.cursor.teenmonitor.backend.plist
   launchctl load ~/Library/LaunchAgents/com.cursor.teenmonitor.agent.plist
   ```

### Using the dashboard

- **On the same laptop:** Open **http://localhost:8000** in a browser. The backend serves the parent dashboard at `/`; set the API key in the UI if needed and click Save / Refresh.
- **From another device (e.g. parent's phone):** Open **http://&lt;teen-laptop-ip&gt;:8000** (find the laptop's IP in System Settings → Network). In the dashboard, set API URL to that address and the same API key.

### Stop or restart

- Unload (stop):  
  `launchctl unload ~/Library/LaunchAgents/com.cursor.teenmonitor.backend.plist`  
  `launchctl unload ~/Library/LaunchAgents/com.cursor.teenmonitor.agent.plist`
- Reload after changing plists or config: unload then load again.

### Logs

- Backend: `/tmp/teenmonitor-backend.log` and `/tmp/teenmonitor-backend.err`
- Agent: `/tmp/teenmonitor-agent.log` and `/tmp/teenmonitor-agent.err`

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
