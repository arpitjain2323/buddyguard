"""
macOS screen capture. Requires Screen Recording permission.
Uses screencapture CLI for simplicity; optional PyObjC/Quartz for in-memory.
"""
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from PIL import Image


def capture_screen(output_path: Optional[Path] = None) -> Optional[Image.Image]:
    """
    Capture the main display. Returns PIL Image or None on failure.
    If output_path is given, also saves to file.
    """
    path = output_path or Path(tempfile.gettempdir()) / f"screen_{int(time.time())}.png"
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    except Exception:
        if not output_path and path.exists():
            path.unlink(missing_ok=True)
        return None
