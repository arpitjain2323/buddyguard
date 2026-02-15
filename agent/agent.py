"""
Teen Compute & Safety Agent - main loop.
Orchestrates screen capture, usage tracking, harmful content classification,
and pushes events to the parent backend.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from agent.capture import capture_screen
from agent.usage import UsageTracker
from agent.classifier import HarmfulContentClassifier, HarmfulResult


def load_config(config_path: Optional[Path] = None) -> dict:
    path = config_path or Path(__file__).parent / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def send_event(backend_url: str, api_key: str, device_id: str, event: dict) -> bool:
    """POST event to backend."""
    try:
        import requests
        r = requests.post(
            f"{backend_url.rstrip('/')}/api/events",
            json={
                "device_id": device_id,
                "timestamp": time.time(),
                **event,
            },
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=15,
        )
        ok = r.status_code in (200, 201)
        if not ok:
            log.warning("Backend rejected event: %s %s", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        log.warning("Failed to send event: %s", e)
        return False


def main_loop(config_path: Optional[Path] = None):
    config = load_config(config_path)
    device_id = config.get("device_id", "unknown")
    backend_cfg = config.get("backend", {})
    backend_url = backend_cfg.get("url", "http://localhost:8000")
    api_key = os.environ.get("BACKEND_API_KEY") or backend_cfg.get("api_key", "")
    upload_interval = backend_cfg.get("upload_interval_seconds", 60)

    capture_cfg = config.get("capture", {})
    capture_enabled = capture_cfg.get("enabled", True)
    capture_interval = capture_cfg.get("interval_seconds", 60)
    classifier_run_every_n = max(1, capture_cfg.get("classifier_run_every_n", 1))
    screenshot_dir = capture_cfg.get("screenshot_dir")
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    store_screenshot = capture_cfg.get("store_screenshot_on_alert", False)

    classifier_cfg = config.get("classifier", {})
    classifier_enabled = classifier_cfg.get("enabled", True)
    cooldown = classifier_cfg.get("alert_cooldown_seconds", 300)
    confidence_threshold = classifier_cfg.get("confidence_threshold", 0.7)
    provider = (classifier_cfg.get("provider") or "openai").lower()
    openai_key = os.environ.get("OPENAI_API_KEY") or classifier_cfg.get("openai_api_key", "")
    use_keyword = provider == "keyword"
    use_openai = provider == "openai" and bool(openai_key)
    classifier = None
    if classifier_enabled and (use_openai or use_keyword):
        classifier = HarmfulContentClassifier(
            api_key=openai_key or "",
            categories=classifier_cfg.get("categories"),
            confidence_threshold=confidence_threshold,
            use_vision=use_openai,
            provider=provider,
            keywords=classifier_cfg.get("keywords"),
        )

    usage_cfg = config.get("usage", {})
    tracker = UsageTracker(
        track_time=usage_cfg.get("track_time", True),
        track_active_app=usage_cfg.get("track_active_app", True),
        track_window_title=usage_cfg.get("track_window_title", True),
        track_cpu_memory=usage_cfg.get("track_cpu_memory", False),
        track_browser_url=usage_cfg.get("track_browser_url", True),
        poll_interval_seconds=usage_cfg.get("poll_interval_seconds", 10),
    )

    last_upload = 0.0
    last_capture = 0.0
    capture_count = 0

    log.info(
        "Agent started | device_id=%s | backend=%s | upload_every=%ss | capture=%s (every %ss) | classifier=%s",
        device_id,
        backend_url,
        upload_interval,
        "on" if capture_enabled else "off",
        capture_interval,
        "on" if classifier else "off",
    )

    while True:
        now = time.time()

        # Usage poll
        tracker.poll()

        # Periodic usage upload
        if now - last_upload >= upload_interval:
            summary = tracker.get_summary()
            ok = send_event(
                backend_url,
                api_key,
                device_id,
                {"type": "usage_summary", "payload": summary},
            )
            if ok:
                total_min = int((summary.get("total_seconds") or 0) / 60)
                apps = summary.get("app_seconds") or {}
                log.info("Usage uploaded | total=%s min | apps=%s", total_min, list(apps.keys())[:5])
            last_upload = now

        # Screen capture + harmful content check (skipped if capture.enabled: false)
        if capture_enabled and now - last_capture >= capture_interval:
            last_capture = now
            capture_count += 1
            out_path = None
            if screenshot_dir:
                out_path = Path(screenshot_dir) / f"screen_{int(now)}.png"
            img = capture_screen(output_path=out_path)
            if img:
                if out_path:
                    log.info("Screenshot saved: %s", out_path)
            run_classifier = classifier and (capture_count % classifier_run_every_n == 0)
            if img and run_classifier:
                result = classifier.check_image(img)
                if result.flagged and result.confidence >= confidence_threshold:
                    if not classifier.apply_cooldown(result.categories, cooldown):
                        ctx = tracker.get_current_context()
                        payload = {
                            "categories": result.categories,
                            "confidence": result.confidence,
                            "details": result.details,
                            "app": ctx.get("app"),
                            "url": ctx.get("url"),
                            "title": ctx.get("title"),
                        }
                        if store_screenshot:
                            # Optional: save redacted thumbnail and attach URL/path
                            pass
                        send_event(
                            backend_url,
                            api_key,
                            device_id,
                            {"type": "harmful_content_alert", "payload": payload},
                        )
                        log.info("Alert sent: %s", payload.get("categories"))

        sleep_sec = min(usage_cfg.get("poll_interval_seconds", 15), capture_interval, upload_interval) / 2.0
        time.sleep(max(5.0, sleep_sec))


if __name__ == "__main__":
    main_loop()
