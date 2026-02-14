"""
Parent backend: ingest events from teen agent, store them, serve API for dashboard.
"""
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# In-memory store (replace with DB for production). Capped to avoid unbounded growth.
EVENTS_MAX = 5000
EVENTS: List[dict] = []


def get_api_key():
    return os.environ.get("BACKEND_API_KEY", "dev-key-change-me")


class EventIn(BaseModel):
    device_id: str
    timestamp: float
    type: str  # usage_summary | harmful_content_alert
    payload: Optional[dict] = None


app = FastAPI(title="Teen Monitor Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def auth(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization")
    key = authorization.split(" ", 1)[1]
    if key != get_api_key():
        raise HTTPException(401, "Invalid API key")


@app.post("/api/events")
def post_event(event: EventIn, authorization: Optional[str] = Header(None)):
    auth(authorization)
    record = {
        "device_id": event.device_id,
        "timestamp": event.timestamp,
        "type": event.type,
        "payload": event.payload or {},
    }
    EVENTS.append(record)
    if len(EVENTS) > EVENTS_MAX:
        EVENTS[:] = EVENTS[-EVENTS_MAX:]
    return {"ok": True, "id": len(EVENTS) - 1}


@app.get("/api/events")
def get_events(
    device_id: Optional[str] = None,
    type: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 200,
    authorization: Optional[str] = Header(None),
):
    auth(authorization)
    out = list(EVENTS)
    if device_id:
        out = [e for e in out if e.get("device_id") == device_id]
    if type:
        out = [e for e in out if e.get("type") == type]
    if since is not None:
        out = [e for e in out if e.get("timestamp", 0) >= since]
    out.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return {"events": out[:limit]}


@app.get("/api/usage/summary")
def get_usage_summary(
    device_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    auth(authorization)
    usage_events = [e for e in EVENTS if e.get("type") == "usage_summary"]
    if device_id:
        usage_events = [e for e in usage_events if e.get("device_id") == device_id]
    if not usage_events:
        return {"summary": None, "recent": []}
    latest = max(usage_events, key=lambda e: e.get("timestamp", 0))
    return {
        "summary": latest.get("payload"),
        "recent": sorted(usage_events, key=lambda e: e.get("timestamp", 0), reverse=True)[:20],
    }


@app.get("/api/alerts")
def get_alerts(
    device_id: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 100,
    authorization: Optional[str] = Header(None),
):
    auth(authorization)
    alerts = [e for e in EVENTS if e.get("type") == "harmful_content_alert"]
    if device_id:
        alerts = [e for e in alerts if e.get("device_id") == device_id]
    if since is not None:
        alerts = [e for e in alerts if e.get("timestamp", 0) >= since]
    alerts.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return {"alerts": alerts[:limit]}


# Serve parent dashboard at / (after API routes so /api/* takes precedence)
_dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
if _dashboard_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_dashboard_dir), html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
