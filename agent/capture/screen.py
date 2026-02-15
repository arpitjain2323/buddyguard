"""
macOS screen capture. Requires Screen Recording permission.
Uses Quartz (Core Graphics) in-process to capture the frontmost app's window when possible,
so the same Python process that has permission captures the real content instead of
desktop/screensaver when run as a LaunchAgent. Falls back to screencapture CLI.
"""
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from PIL import Image

log = logging.getLogger(__name__)

# Quartz option values (Apple headers) if attr not on Quartz
_OPTS = {
    "kCGWindowListOptionOnScreenOnly": 1 << 0,
    "kCGWindowListOptionIncludingWindow": 1 << 1,
    "kCGWindowListExcludeDesktopElements": 1 << 9,
}
_kCGNullWindowID = 0


def _get_frontmost_pid() -> Optional[int]:
    """Return PID of the frontmost application, or None. Uses AppleScript."""
    try:
        out = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get unix id of first application process whose frontmost is true',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout:
            return int(out.stdout.strip())
    except Exception:
        pass
    return None


def _get_window_id_for_pid(pid: int) -> Optional[int]:
    """Return the first (frontmost) window ID owned by the given PID, or None."""
    try:
        import Quartz

        opts = getattr(
            Quartz,
            "kCGWindowListOptionOnScreenOnly",
            _OPTS["kCGWindowListOptionOnScreenOnly"],
        ) | getattr(
            Quartz,
            "kCGWindowListExcludeDesktopElements",
            _OPTS["kCGWindowListExcludeDesktopElements"],
        )
        null_id = getattr(Quartz, "kCGNullWindowID", _kCGNullWindowID)
        window_list = Quartz.CGWindowListCopyWindowInfo(opts, null_id)
        if not window_list:
            return None
        pid_key = getattr(Quartz, "kCGWindowOwnerPID", "kCGWindowOwnerPID")
        num_key = getattr(Quartz, "kCGWindowNumber", "kCGWindowNumber")
        for w in window_list:
            if w.get(pid_key) != pid:
                continue
            # Skip clearly desktop/screensaver windows
            owner_key = getattr(Quartz, "kCGWindowOwnerName", "kCGWindowOwnerName")
            owner = str(w.get(owner_key) or "")
            if owner in ("Window Server", "ScreenSaverEngine", "loginwindow"):
                continue
            wid = w.get(num_key)
            if wid is not None:
                return int(wid)
        return None
    except Exception:
        return None


def _cgimage_to_pil(cgimage) -> Optional[Image.Image]:
    """Convert a Quartz CGImage to PIL Image. Handles BGRA and row stride."""
    try:
        import Quartz

        w = Quartz.CGImageGetWidth(cgimage)
        h = Quartz.CGImageGetHeight(cgimage)
        bpr = Quartz.CGImageGetBytesPerRow(cgimage)
        provider = Quartz.CGImageGetDataProvider(cgimage)
        data = Quartz.CGDataProviderCopyData(provider)
        if data is None:
            return None
        # NSData from PyObjC: get bytes
        if hasattr(data, "bytes"):
            raw = data.bytes()
        elif isinstance(data, (bytes, bytearray)):
            raw = data
        else:
            raw = bytes(data)
        # Pixel format is typically BGRA; row stride may be >= width*4
        rgb = bytearray(w * h * 3)
        for y in range(h):
            row_start = y * bpr
            for x in range(w):
                px = row_start + x * 4
                b, g, r = raw[px], raw[px + 1], raw[px + 2]
                out_idx = (y * w + x) * 3
                rgb[out_idx] = r
                rgb[out_idx + 1] = g
                rgb[out_idx + 2] = b
        return Image.frombytes("RGB", (w, h), bytes(rgb))
    except Exception as e:
        log.debug("CGImage to PIL failed: %s", e)
        return None


def _capture_window_quartz(window_id: int):
    """Capture a single window by ID using Quartz. Returns PIL Image or None."""
    try:
        import Quartz

        inc = getattr(
            Quartz,
            "kCGWindowListOptionIncludingWindow",
            _OPTS["kCGWindowListOptionIncludingWindow"],
        )
        null_rect = getattr(Quartz, "CGRectNull", None)
        if null_rect is None:
            null_rect = Quartz.CGRectMake(0, 0, 0, 0)
        opts_img = getattr(Quartz, "kCGWindowImageDefault", 0)
        cg = Quartz.CGWindowListCreateImage(
            null_rect,
            inc,
            window_id,
            opts_img,
        )
        if cg is not None:
            return _cgimage_to_pil(cg)
    except Exception as e:
        log.debug("Quartz window capture failed: %s", e)
    return None


def _capture_fullscreen_quartz() -> Optional[Image.Image]:
    """Capture full screen using Quartz in-process. Returns PIL Image or None."""
    try:
        import Quartz

        inf = getattr(Quartz, "CGRectInfinite", None)
        if inf is None:
            inf = Quartz.CGRectMake(-1e6, -1e6, 2e6, 2e6)
        on_screen = getattr(
            Quartz,
            "kCGWindowListOptionOnScreenOnly",
            _OPTS["kCGWindowListOptionOnScreenOnly"],
        )
        null_id = getattr(Quartz, "kCGNullWindowID", _kCGNullWindowID)
        opts_img = getattr(Quartz, "kCGWindowImageDefault", 0)
        cg = Quartz.CGWindowListCreateImage(inf, on_screen, null_id, opts_img)
        if cg is not None:
            return _cgimage_to_pil(cg)
    except Exception as e:
        log.debug("Quartz fullscreen capture failed: %s", e)
    return None


def capture_screen(output_path: Optional[Path] = None) -> Optional[Image.Image]:
    """
    Capture the frontmost app's window (or full screen). Prefers Quartz in-process
    so the Python process that has Screen Recording permission gets real content.
    If output_path is given, saves to file as well.
    """
    img = None
    # 1) Frontmost app's window via Quartz (in-process)
    pid = _get_frontmost_pid()
    if pid is not None:
        wid = _get_window_id_for_pid(pid)
        if wid is not None:
            img = _capture_window_quartz(wid)
            if img is not None:
                log.debug("Captured frontmost window (PID %s, WID %s)", pid, wid)
    # 2) Full screen via Quartz (in-process)
    if img is None:
        img = _capture_fullscreen_quartz()
        if img is not None:
            log.debug("Captured full screen via Quartz")
    # 3) Fallback: screencapture CLI (frontmost window then full screen)
    if img is None:
        path = output_path or Path(tempfile.gettempdir()) / f"screen_{int(time.time())}.png"
        wid = None
        if pid is not None:
            wid = _get_window_id_for_pid(pid)
        cmd = ["screencapture", "-x", "-t", "png", str(path)]
        if wid is not None:
            cmd = ["screencapture", "-l", str(wid), "-x", "-t", "png", str(path)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=10, check=True)
            img = Image.open(path).convert("RGB")
            if output_path is None:
                path.unlink(missing_ok=True)
            log.debug("Captured via screencapture (window=%s)", wid)
        except Exception:
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
            except Exception:
                pass
        if img is None and not output_path and path.exists():
            path.unlink(missing_ok=True)

    if img is not None and output_path is not None:
        try:
            img.save(str(output_path))
        except Exception:
            pass
    return img
