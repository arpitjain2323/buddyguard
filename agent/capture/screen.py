"""
macOS screen capture. Requires Screen Recording permission.
Captures the frontmost window when possible (so content is visible when run as LaunchAgent);
falls back to full-screen capture.
"""
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from PIL import Image

# Quartz constants (fallback if import fails)
_kCGWindowListOptionOnScreenOnly = 1 << 0
_kCGWindowListExcludeDesktopElements = 1 << 9
_kCGNullWindowID = 0


def _get_frontmost_window_id() -> Optional[int]:
    """Return the window ID of the frontmost on-screen window, or None.
    Requires Screen Recording (and optionally Accessibility). When the agent runs
    as a LaunchAgent, capturing this window often yields the actual app content
    instead of just the desktop/screensaver.
    """
    try:
        import Quartz

        opts = (
            getattr(Quartz, "kCGWindowListOptionOnScreenOnly", _kCGWindowListOptionOnScreenOnly)
            | getattr(
                Quartz,
                "kCGWindowListExcludeDesktopElements",
                _kCGWindowListExcludeDesktopElements,
            )
        )
        null_id = getattr(Quartz, "kCGNullWindowID", _kCGNullWindowID)
        window_list = Quartz.CGWindowListCopyWindowInfo(opts, null_id)
        if not window_list or len(window_list) == 0:
            return None
        # List is front-to-back; first window is frontmost
        first = window_list[0]
        # PyObjC may use the constant or its string name as key
        for key in (
            getattr(Quartz, "kCGWindowNumber", None),
            "kCGWindowNumber",
        ):
            if key is None:
                continue
            wid = first.get(key)
            if wid is not None:
                return int(wid)
        return None
    except Exception:
        return None


def capture_screen(output_path: Optional[Path] = None) -> Optional[Image.Image]:
    """
    Capture the frontmost window (or main display if that fails). Returns PIL Image or None.
    Preferring the frontmost window avoids capturing only the desktop/screensaver when
    the agent runs as a LaunchAgent.
    If output_path is given, also saves to file.
    """
    path = output_path or Path(tempfile.gettempdir()) / f"screen_{int(time.time())}.png"
    window_id = _get_frontmost_window_id()

    cmd = ["screencapture", "-x", "-t", "png", str(path)]
    if window_id is not None:
        cmd = ["screencapture", "-l", str(window_id), "-x", "-t", "png", str(path)]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
            check=True,
        )
        img = Image.open(path).convert("RGB")
        if output_path is None:
            path.unlink(missing_ok=True)
        return img
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        if window_id is not None:
            # Retry without -l (full screen) in case -l failed for this app
            try:
                subprocess.run(
                    ["screencapture", "-x", "-t", "png", str(path)],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                img = Image.open(path).convert("RGB")
                if output_path is None:
                    path.unlink(missing_ok=True)
                return img
            except Exception:
                pass
        return None
    except Exception:
        if not output_path and path.exists():
            path.unlink(missing_ok=True)
        return None
