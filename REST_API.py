from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import uuid

app = FastAPI(
    title="Smart Parking Management System API",
    description="API-first smart parking system with automated entry/exit monitoring via license plate recognition",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOTAL_SPOTS = 50
HOURLY_RATE = 2.50  # dollars per hour
MIN_OCR_CONFIDENCE = 0.6

# ---------------------------------------------------------------------------
# Enums & Models
# ---------------------------------------------------------------------------

class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"
    PAID = "PAID"


class CameraSource(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"


class PlateDetectionRequest(BaseModel):
    license_plate: str
    confidence: float
    camera_source: CameraSource


class PaymentRequest(BaseModel):
    amount: float


# ---------------------------------------------------------------------------
# In-memory stores (will be replaced by MySQL via Database team)
# ---------------------------------------------------------------------------

# FIXME: Replace with MySQL tables once DB team integrates.
#   - parking_sessions  → stores entry/exit records
#   - plate_events      → logs every OCR event for auditing
parking_sessions: dict[str, dict] = {}   # session_id → session data
plate_events: list[dict] = []            # chronological OCR event log
occupied_spots: int = 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_active_session(plate: str) -> Optional[str]:
    """Return session_id of the ACTIVE session for a given plate, or None."""
    for sid, s in parking_sessions.items():
        if s["license_plate"] == plate and s["status"] == SessionStatus.ACTIVE:
            return sid
    return None


def _log_plate_event(plate: str, confidence: float, camera: CameraSource, accepted: bool, reason: str = ""):
    plate_events.append({
        "event_id": str(uuid.uuid4()),
        "license_plate": plate,
        "confidence": confidence,
        "camera_source": camera,
        "accepted": accepted,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
    })


def _calculate_fee(entry_time: datetime, exit_time: datetime) -> float:
    duration_hours = (exit_time - entry_time).total_seconds() / 3600
    return round(max(duration_hours, 0.5) * HOURLY_RATE, 2)  # minimum 30-min charge

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    """API health check with current system time."""
    return {
        "status": "Smart Parking API is Online",
        "system_time": datetime.now(),
        "total_spots": TOTAL_SPOTS,
        "available_spots": TOTAL_SPOTS - occupied_spots,
    }


# ---- Real-time availability (Slide 5 & 6) --------------------------------

@app.get("/api/spots")
def get_availability():
    """Real-time parking spot availability."""
    return {
        "total_spots": TOTAL_SPOTS,
        "occupied": occupied_spots,
        "available": TOTAL_SPOTS - occupied_spots,
        "updated_at": datetime.now(),
    }


# ---- Vehicle Entry (Slide 6 – step 01) -----------------------------------

@app.post("/api/entry")
def vehicle_entry(data: PlateDetectionRequest):
    """
    Process a vehicle entering the parking lot.
    OCR output arrives from the entry camera → log entry, assign spot, decrement availability.
    """
    global occupied_spots

    if data.confidence < MIN_OCR_CONFIDENCE:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, False, "Low OCR confidence")
        raise HTTPException(status_code=400, detail="OCR confidence too low — plate unreadable. Please retry.")

    if occupied_spots >= TOTAL_SPOTS:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, False, "Lot full")
        raise HTTPException(status_code=409, detail="Parking lot is full. No available spots.")

    existing = _find_active_session(data.license_plate)
    if existing:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, False, "Duplicate entry")
        raise HTTPException(
            status_code=409,
            detail=f"Vehicle {data.license_plate} already has an active session ({existing}).",
        )

    session_id = str(uuid.uuid4())
    now = datetime.now()
    parking_sessions[session_id] = {
        "session_id": session_id,
        "license_plate": data.license_plate,
        "entry_time": now.isoformat(),
        "exit_time": None,
        "duration_minutes": None,
        "fee": None,
        "status": SessionStatus.ACTIVE,
    }
    occupied_spots += 1

    _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, True, "Entry recorded")

    return {
        "message": "Entry recorded — gate open",
        "session_id": session_id,
        "license_plate": data.license_plate,
        "entry_time": now,
        "available_spots": TOTAL_SPOTS - occupied_spots,
    }


# ---- Vehicle Exit (Slide 6 – step 03) ------------------------------------

@app.post("/api/exit")
def vehicle_exit(data: PlateDetectionRequest):
    """
    Process a vehicle leaving the parking lot.
    OCR output arrives from the exit camera → compute duration & fee, update session to EXITED.
    """
    global occupied_spots

    if data.confidence < MIN_OCR_CONFIDENCE:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.EXIT, False, "Low OCR confidence")
        raise HTTPException(status_code=400, detail="OCR confidence too low — plate unreadable. Please retry.")

    session_id = _find_active_session(data.license_plate)
    if not session_id:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.EXIT, False, "No active session")
        raise HTTPException(
            status_code=404,
            detail=f"No active parking session found for plate {data.license_plate}.",
        )

    session = parking_sessions[session_id]
    now = datetime.now()
    entry_time = datetime.fromisoformat(session["entry_time"])
    duration = now - entry_time
    fee = _calculate_fee(entry_time, now)

    session["exit_time"] = now.isoformat()
    session["duration_minutes"] = round(duration.total_seconds() / 60, 1)
    session["fee"] = fee
    session["status"] = SessionStatus.EXITED

    occupied_spots = max(occupied_spots - 1, 0)

    _log_plate_event(data.license_plate, data.confidence, CameraSource.EXIT, True, "Exit recorded")

    return {
        "message": "Exit recorded — please proceed to payment",
        "session_id": session_id,
        "license_plate": data.license_plate,
        "entry_time": session["entry_time"],
        "exit_time": now,
        "duration_minutes": session["duration_minutes"],
        "fee": fee,
        "available_spots": TOTAL_SPOTS - occupied_spots,
    }


# ---- Payment confirmation (Slide 6 – manual payment → open gate) ---------

@app.post("/api/payment/{session_id}")
def process_payment(session_id: str, payment: PaymentRequest):
    """
    Mark a session as PAID after manual payment is received.
    Transitions session from EXITED → PAID.
    """
    if session_id not in parking_sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = parking_sessions[session_id]

    if session["status"] == SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Vehicle has not exited yet.")
    if session["status"] == SessionStatus.PAID:
        raise HTTPException(status_code=400, detail="Session already paid.")

    if payment.amount < session["fee"]:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient payment. Required: ${session['fee']}, received: ${payment.amount}",
        )

    session["status"] = SessionStatus.PAID

    return {
        "message": "Payment accepted — gate open",
        "session_id": session_id,
        "license_plate": session["license_plate"],
        "fee_charged": session["fee"],
        "paid_at": datetime.now(),
    }


# ---- Active sessions ------------------------------------------------------

@app.get("/api/sessions/active")
def get_active_sessions():
    """List all vehicles currently parked (ACTIVE sessions)."""
    active = [s for s in parking_sessions.values() if s["status"] == SessionStatus.ACTIVE]
    return {
        "count": len(active),
        "sessions": active,
    }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    """Look up a single parking session by ID."""
    if session_id not in parking_sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    return parking_sessions[session_id]


# ---- OCR Plate Events log (Slide 9 – reliability) -------------------------

@app.get("/api/events")
def get_plate_events(limit: int = Query(default=50, le=200)):
    """Return recent plate-detection events for auditing / debugging."""
    return {
        "total_events": len(plate_events),
        "events": plate_events[-limit:],
    }


# ---- Analytics (Slide 5 & 10 – daily revenue, peak times, repeats) --------

@app.get("/api/analytics/daily")
def daily_analytics():
    """
    Generate daily analytics:
      - Total revenue
      - Number of vehicles served
      - Peak usage hour
      - Repeat-vehicle count
    """
    today = datetime.now().date()
    todays_sessions = [
        s for s in parking_sessions.values()
        if datetime.fromisoformat(s["entry_time"]).date() == today
    ]

    total_revenue = sum(s["fee"] for s in todays_sessions if s["fee"] is not None)
    vehicles_served = len(todays_sessions)

    hour_counts: dict[int, int] = {}
    plate_counts: dict[str, int] = {}
    for s in todays_sessions:
        hour = datetime.fromisoformat(s["entry_time"]).hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
        plate_counts[s["license_plate"]] = plate_counts.get(s["license_plate"], 0) + 1

    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None
    repeat_vehicles = [plate for plate, cnt in plate_counts.items() if cnt > 1]

    return {
        "date": str(today),
        "total_revenue": round(total_revenue, 2),
        "vehicles_served": vehicles_served,
        "currently_parked": sum(1 for s in todays_sessions if s["status"] == SessionStatus.ACTIVE),
        "peak_hour": f"{peak_hour}:00" if peak_hour is not None else "N/A",
        "repeat_vehicles": repeat_vehicles,
    }
