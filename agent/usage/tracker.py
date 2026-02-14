"""
Compute usage tracker: active app, foreground time, optional CPU/memory.
When Google Chrome is frontmost, optionally tracks per-URL time (via AppleScript).
Uses psutil and (on macOS) subprocess for frontmost application.
"""
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse

import psutil


@dataclass
class UsageSnapshot:
    timestamp: float
    active_app: Optional[str] = None
    window_title: Optional[str] = None
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None


def _get_frontmost_app_macos() -> tuple[Optional[str], Optional[str]]:
    """Get frontmost app name and window title on macOS via AppleScript.
    Requires Accessibility permission for Terminal (or the process running the agent).
    """
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    try:
        # Get frontmost app name first (most reliable; needs Accessibility)
        out = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout:
            app_name = out.stdout.strip() or None
        if not app_name:
            return (None, None)
        # Optionally get window title (can fail for some apps if no window or permission)
        out2 = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of front window of first application process whose frontmost is true'],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out2.returncode == 0 and out2.stdout and out2.stdout.strip():
            window_title = out2.stdout.strip()
    except Exception:
        pass
    return (app_name, window_title)


def _get_chrome_url_and_title_macos() -> tuple[Optional[str], Optional[str]]:
    """Get URL and title of the active tab in Google Chrome in one AppleScript call. Returns (url, title)."""
    try:
        script = (
            'tell application "Google Chrome" to set tabInfo to (get URL of active tab of front window) & "|||" & (get title of active tab of front window)'
            "\nreturn tabInfo"
        )
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode == 0 and out.stdout and "|||" in out.stdout:
            url_part, title_part = out.stdout.strip().split("|||", 1)
            url = url_part.strip() or None
            title = title_part.strip() or None
            return (url, title)
    except Exception:
        pass
    return (None, None)


def _normalize_url(url: str) -> str:
    """Return full URL with fragment (#) stripped for use as key. Keeps path and query."""
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            path = p.path or "/"
            if p.query:
                return f"{p.scheme}://{p.netloc}{path}?{p.query}"
            return f"{p.scheme}://{p.netloc}{path}"
    except Exception:
        pass
    return url


class UsageTracker:
    """Tracks compute usage over time and builds per-app duration summaries."""

    def __init__(
        self,
        track_time: bool = True,
        track_active_app: bool = True,
        track_window_title: bool = True,
        track_cpu_memory: bool = False,
        track_browser_url: bool = True,
        poll_interval_seconds: float = 10.0,
    ):
        self.track_time = track_time
        self.track_active_app = track_active_app
        self.track_window_title = track_window_title
        self.track_cpu_memory = track_cpu_memory
        self.track_browser_url = track_browser_url
        self.poll_interval = poll_interval_seconds
        self._last_snapshot: Optional[UsageSnapshot] = None
        self._app_seconds: Dict[str, float] = {}
        self._url_seconds: Dict[str, float] = {}
        self._url_titles: Dict[str, str] = {}  # url -> page title
        self._last_url: Optional[str] = None
        self._prev_chrome_url: Optional[str] = None
        self._session_start = time.time()

    def poll(self) -> UsageSnapshot:
        """Take a snapshot and update per-app durations."""
        now = time.time()
        app_name, window_title = (None, None)
        if self.track_active_app or self.track_window_title:
            app_name, window_title = _get_frontmost_app_macos()
        cpu = memory_mb = None
        if self.track_cpu_memory and app_name:
            for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
                try:
                    if p.info.get("name") == app_name:
                        p.cpu_percent()
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            time.sleep(0.1)
            for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
                try:
                    if p.info.get("name") == app_name:
                        cpu = p.cpu_percent()
                        mem = p.memory_info()
                        memory_mb = mem.rss / (1024 * 1024)
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        snap = UsageSnapshot(
            timestamp=now,
            active_app=app_name if self.track_active_app else None,
            window_title=window_title if self.track_window_title else None,
            cpu_percent=cpu,
            memory_mb=memory_mb,
        )
        # Update app duration
        elapsed = 0.0
        if self._last_snapshot:
            elapsed = now - self._last_snapshot.timestamp
            if self._last_snapshot.active_app:
                key = self._last_snapshot.active_app
                self._app_seconds[key] = self._app_seconds.get(key, 0) + elapsed

        # When Chrome is frontmost, get active tab URL and track per-URL time
        if self.track_browser_url and self._last_snapshot and self._last_snapshot.active_app == "Google Chrome" and elapsed > 0 and self._prev_chrome_url:
            self._url_seconds[self._prev_chrome_url] = self._url_seconds.get(self._prev_chrome_url, 0) + elapsed
        if self.track_browser_url and app_name == "Google Chrome":
            url, title = _get_chrome_url_and_title_macos()
            if url and not url.startswith(("chrome://", "about:")):
                full_url = _normalize_url(url)
                self._last_url = full_url
                self._prev_chrome_url = full_url
                if title:
                    self._url_titles[full_url] = title
            else:
                self._prev_chrome_url = None
        else:
            self._prev_chrome_url = None

        self._last_snapshot = snap
        return snap

    def get_current_context(self) -> dict:
        """Return current app and, if Chrome, URL and title. Used when attaching context to alerts."""
        out: Dict[str, Optional[str]] = {"app": None}
        if self._last_snapshot and self._last_snapshot.active_app:
            out["app"] = self._last_snapshot.active_app
            if self._last_snapshot.active_app == "Google Chrome" and self._last_url:
                out["url"] = self._last_url
                out["title"] = self._url_titles.get(self._last_url)
        return out

    def get_summary(self) -> dict:
        """Return usage summary for the current session."""
        total_seconds = time.time() - self._session_start
        out = {
            "session_start_ts": self._session_start,
            "total_seconds": total_seconds,
            "app_seconds": dict(self._app_seconds),
            "last_app": self._last_snapshot.active_app if self._last_snapshot else None,
            "last_window_title": self._last_snapshot.window_title if self._last_snapshot else None,
        }
        if self._url_seconds or self._last_url:
            out["url_seconds"] = dict(self._url_seconds)
            out["last_url"] = self._last_url
            if self._url_titles:
                out["url_titles"] = dict(self._url_titles)
        return out
