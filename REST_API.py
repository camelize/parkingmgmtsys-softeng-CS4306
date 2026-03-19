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

# ===========================================================================
# Configuration — adjust these values as needed for the demo
# ===========================================================================
TOTAL_SPOTS = 50              # Total parking spots in the lot
HOURLY_RATE = 2.50            # Fee in dollars per hour
MIN_OCR_CONFIDENCE = 0.6      # Minimum confidence score to accept a plate read
#   ▲ [OCR Team] If Tesseract consistently returns lower scores,
#     we can discuss lowering this threshold or adding a retry mechanism.

# ===========================================================================
# Enums & Models — shared data contracts between OCR, API, and DB
# ===========================================================================

class SessionStatus(str, Enum):
    """
    Parking session lifecycle:
        ACTIVE  → vehicle is currently parked
        EXITED  → vehicle left, fee calculated, awaiting payment
        PAID    → payment received, session closed

    [DB Team] This maps to a VARCHAR or ENUM column in the parking_sessions table.
    """
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"
    PAID = "PAID"


class CameraSource(str, Enum):
    """
    Which physical camera captured the plate.

    [OCR Team] Set this to "entry" for the gate-in camera,
    "exit" for the gate-out camera. The API uses this value to decide
    whether to create a new session (entry) or close one (exit).
    """
    ENTRY = "entry"
    EXIT = "exit"


class PlateDetectionRequest(BaseModel):
    """
    The JSON body that the OCR pipeline sends to the API on every detection.

    [OCR Team] After Tesseract extracts the plate text, POST this to
    /api/entry (gate-in camera) or /api/exit (gate-out camera).

    Example JSON:
        {
            "license_plate": "ABC1234",
            "confidence": 0.92,
            "camera_source": "entry"
        }

    Fields:
        license_plate  — the text string extracted by Tesseract
        confidence     — Tesseract's confidence score (0.0 – 1.0)
        camera_source  — "entry" or "exit" depending on which gate camera
    """
    license_plate: str
    confidence: float
    camera_source: CameraSource


class PaymentRequest(BaseModel):
    """
    Body for the payment endpoint. In the demo, payment is handled manually
    (cash / external system), so this just records the amount received.
    """
    amount: float


# ===========================================================================
# In-memory data stores
#
# [DB Team – INTEGRATION POINT]
# Everything below is temporary. Replace with MySQL queries once ready.
#
# Suggested MySQL tables:
#
#   parking_sessions
#   ┌──────────────┬──────────────┬─────────────┬─────────────┬──────────────┬───────┬────────┐
#   │ session_id   │ license_plate│ entry_time  │ exit_time   │ duration_min │ fee   │ status │
#   │ (PK, UUID)   │ VARCHAR(20)  │ DATETIME    │ DATETIME    │ FLOAT        │ FLOAT │ ENUM   │
#   └──────────────┴──────────────┴─────────────┴─────────────┴──────────────┴───────┴────────┘
#
#   plate_events  (audit / debugging log)
#   ┌──────────────┬──────────────┬────────────┬───────────────┬──────────┬──────────┬───────────┐
#   │ event_id     │ license_plate│ confidence │ camera_source │ accepted │ reason   │ timestamp │
#   │ (PK, UUID)   │ VARCHAR(20)  │ FLOAT      │ ENUM          │ BOOLEAN  │ TEXT     │ DATETIME  │
#   └──────────────┴──────────────┴────────────┴───────────────┴──────────┴──────────┴───────────┘
#
# ===========================================================================

parking_sessions: dict[str, dict] = {}   # session_id → session data
plate_events: list[dict] = []            # chronological OCR event log
occupied_spots: int = 0                  # current number of occupied spots

# ===========================================================================
# Helper functions
# ===========================================================================

def _find_active_session(plate: str) -> Optional[str]:
    """
    Look up whether this plate already has an ACTIVE (parked) session.

    [DB Team] Replace with:
        SELECT session_id FROM parking_sessions
        WHERE license_plate = :plate AND status = 'ACTIVE'
        LIMIT 1;
    """
    for sid, s in parking_sessions.items():
        if s["license_plate"] == plate and s["status"] == SessionStatus.ACTIVE:
            return sid
    return None


def _log_plate_event(plate: str, confidence: float, camera: CameraSource, accepted: bool, reason: str = ""):
    """
    Record every OCR detection attempt — both accepted and rejected.

    [DB Team] Replace with:
        INSERT INTO plate_events
            (event_id, license_plate, confidence, camera_source, accepted, reason, timestamp)
        VALUES (:id, :plate, :conf, :cam, :accepted, :reason, NOW());

    [OCR Team] This is where we track accuracy stats. You can query
    GET /api/events to see if your detections are being accepted or rejected.
    """
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
    """
    Fee = hours_parked × HOURLY_RATE, with a minimum 30-minute charge.
    Example: 2 hours parked → 2 × $2.50 = $5.00
    """
    duration_hours = (exit_time - entry_time).total_seconds() / 3600
    return round(max(duration_hours, 0.5) * HOURLY_RATE, 2)

# ===========================================================================
# Endpoints
# ===========================================================================

@app.get("/")
def home():
    """API health check — useful for display clients to verify the server is up."""
    return {
        "status": "Smart Parking API is Online",
        "system_time": datetime.now(),
        "total_spots": TOTAL_SPOTS,
        "available_spots": TOTAL_SPOTS - occupied_spots,
    }


# ---------------------------------------------------------------------------
# Real-time availability
#   Used by Bunlong's Raspberry Pi / Arduino display client to show open spots.
# ---------------------------------------------------------------------------

@app.get("/api/spots")
def get_availability():
    """
    Returns current parking availability.

    [DB Team] Once integrated, occupied count should come from:
        SELECT COUNT(*) FROM parking_sessions WHERE status = 'ACTIVE';
    """
    return {
        "total_spots": TOTAL_SPOTS,
        "occupied": occupied_spots,
        "available": TOTAL_SPOTS - occupied_spots,
        "updated_at": datetime.now(),
    }


# ---------------------------------------------------------------------------
# Vehicle Entry
#
# [OCR Team] This is the endpoint your entry-gate camera calls.
#   After OpenCV + Tesseract extracts the plate string:
#     POST /api/entry
#     Body: { "license_plate": "ABC1234", "confidence": 0.92, "camera_source": "entry" }
#
#   Possible responses:
#     200 → entry accepted, gate should open
#     400 → OCR confidence too low, re-capture needed
#     409 → lot full OR plate already has an active session
# ---------------------------------------------------------------------------

@app.post("/api/entry")
def vehicle_entry(data: PlateDetectionRequest):
    global occupied_spots

    # [OCR Team] Reject if confidence is below threshold — trigger a re-scan
    if data.confidence < MIN_OCR_CONFIDENCE:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, False, "Low OCR confidence")
        raise HTTPException(status_code=400, detail="OCR confidence too low — plate unreadable. Please retry.")

    # Check lot capacity before allowing entry
    if occupied_spots >= TOTAL_SPOTS:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, False, "Lot full")
        raise HTTPException(status_code=409, detail="Parking lot is full. No available spots.")

    # Prevent duplicate entry — same plate can't enter twice without exiting
    existing = _find_active_session(data.license_plate)
    if existing:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, False, "Duplicate entry")
        raise HTTPException(
            status_code=409,
            detail=f"Vehicle {data.license_plate} already has an active session ({existing}).",
        )

    # --- Create new parking session ---
    # [DB Team] Replace with INSERT INTO parking_sessions (...)
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
    occupied_spots += 1  # [DB Team] Derive from COUNT(*) WHERE status='ACTIVE' instead

    _log_plate_event(data.license_plate, data.confidence, CameraSource.ENTRY, True, "Entry recorded")

    return {
        "message": "Entry recorded — gate open",
        "session_id": session_id,
        "license_plate": data.license_plate,
        "entry_time": now,
        "available_spots": TOTAL_SPOTS - occupied_spots,
    }


# ---------------------------------------------------------------------------
# Vehicle Exit
#
# [OCR Team] This is the endpoint your exit-gate camera calls.
#   After OpenCV + Tesseract extracts the plate string:
#     POST /api/exit
#     Body: { "license_plate": "ABC1234", "confidence": 0.88, "camera_source": "exit" }
#
#   Possible responses:
#     200 → exit recorded, fee calculated, proceed to payment
#     400 → OCR confidence too low, re-capture needed
#     404 → no active session for this plate (vehicle never entered?)
# ---------------------------------------------------------------------------

@app.post("/api/exit")
def vehicle_exit(data: PlateDetectionRequest):
    global occupied_spots

    # [OCR Team] Same confidence check as entry
    if data.confidence < MIN_OCR_CONFIDENCE:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.EXIT, False, "Low OCR confidence")
        raise HTTPException(status_code=400, detail="OCR confidence too low — plate unreadable. Please retry.")

    # Find the matching ACTIVE session for this plate
    session_id = _find_active_session(data.license_plate)
    if not session_id:
        _log_plate_event(data.license_plate, data.confidence, CameraSource.EXIT, False, "No active session")
        raise HTTPException(
            status_code=404,
            detail=f"No active parking session found for plate {data.license_plate}.",
        )

    # --- Calculate duration & fee, then update session to EXITED ---
    # [DB Team] Replace with:
    #   UPDATE parking_sessions
    #   SET exit_time = NOW(),
    #       duration_minutes = TIMESTAMPDIFF(MINUTE, entry_time, NOW()),
    #       fee = <calculated>,
    #       status = 'EXITED'
    #   WHERE session_id = :sid;
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


# ---------------------------------------------------------------------------
# Payment confirmation
#   Manual payment at the exit booth → staff confirms via this endpoint.
#   Transitions session: EXITED → PAID
# ---------------------------------------------------------------------------

@app.post("/api/payment/{session_id}")
def process_payment(session_id: str, payment: PaymentRequest):
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

    # [DB Team] Replace with:
    #   UPDATE parking_sessions SET status = 'PAID' WHERE session_id = :sid;
    session["status"] = SessionStatus.PAID

    return {
        "message": "Payment accepted — gate open",
        "session_id": session_id,
        "license_plate": session["license_plate"],
        "fee_charged": session["fee"],
        "paid_at": datetime.now(),
    }


# ---------------------------------------------------------------------------
# Active sessions — shows all vehicles currently parked
# ---------------------------------------------------------------------------

@app.get("/api/sessions/active")
def get_active_sessions():
    """
    [DB Team] Replace with:
        SELECT * FROM parking_sessions WHERE status = 'ACTIVE';
    """
    active = [s for s in parking_sessions.values() if s["status"] == SessionStatus.ACTIVE]
    return {
        "count": len(active),
        "sessions": active,
    }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    """
    [DB Team] Replace with:
        SELECT * FROM parking_sessions WHERE session_id = :sid;
    """
    if session_id not in parking_sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    return parking_sessions[session_id]


# ---------------------------------------------------------------------------
# OCR Plate Events log — every detection attempt is recorded here
#
# [OCR Team] Use GET /api/events to review your detection history.
#   Each event shows whether the plate was accepted or rejected and why.
#   Useful for debugging low-confidence reads or repeated failures.
# ---------------------------------------------------------------------------

@app.get("/api/events")
def get_plate_events(limit: int = Query(default=50, le=200)):
    """
    [DB Team] Replace with:
        SELECT * FROM plate_events ORDER BY timestamp DESC LIMIT :limit;
    """
    return {
        "total_events": len(plate_events),
        "events": plate_events[-limit:],
    }


# ---------------------------------------------------------------------------
# Daily Analytics
#   Revenue report, peak-hour analysis, and repeat-vehicle detection.
# ---------------------------------------------------------------------------

@app.get("/api/analytics/daily")
def daily_analytics():
    """
    [DB Team] This endpoint will benefit most from SQL aggregation:
        - Total revenue:   SELECT SUM(fee) FROM parking_sessions WHERE DATE(entry_time) = CURDATE();
        - Peak hour:       SELECT HOUR(entry_time) as h, COUNT(*) as c ... GROUP BY h ORDER BY c DESC LIMIT 1;
        - Repeat vehicles: SELECT license_plate, COUNT(*) as c ... GROUP BY license_plate HAVING c > 1;
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
