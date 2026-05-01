from datetime import datetime
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import (
    DetectionEvent,
    DetectionLog,
    ParkingSpot,
    VehicleVisit,
    VisitStatus,
    get_db,
    init_db,
)

app = FastAPI(
    title="Smart Parking Management System API",
    description="API-first smart parking system with automated entry/exit monitoring via license plate recognition",
    version="1.0.0",
)

TOTAL_SPOTS = 50
HOURLY_RATE = 2.50
MIN_OCR_CONFIDENCE = 0.6


class CameraSource(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"


class PlateDetectionRequest(BaseModel):
    license_plate: str
    confidence: float
    camera_source: CameraSource


class PaymentRequest(BaseModel):
    amount: float


@app.on_event("startup")
def startup() -> None:
    init_db(TOTAL_SPOTS)


def _normalize_plate(plate: str) -> str:
    return plate.strip().upper()


def _calculate_fee(entry_time: datetime, exit_time: datetime) -> float:
    duration_hours = (exit_time - entry_time).total_seconds() / 3600
    return round(max(duration_hours, 0.5) * HOURLY_RATE, 2)


def _event_type_for_camera(camera: CameraSource) -> DetectionEvent:
    if camera == CameraSource.ENTRY:
        return DetectionEvent.ENTRY_SCAN
    return DetectionEvent.EXIT_SCAN


def _find_active_visit(db: Session, plate: str) -> VehicleVisit | None:
    return db.scalars(
        select(VehicleVisit)
        .where(VehicleVisit.license_plate == plate)
        .where(VehicleVisit.status == VisitStatus.ACTIVE)
        .limit(1)
    ).first()


def _occupied_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(VehicleVisit).where(VehicleVisit.status == VisitStatus.ACTIVE)
    ) or 0


def _get_open_spot(db: Session) -> ParkingSpot | None:
    return db.scalars(
        select(ParkingSpot).where(ParkingSpot.is_occupied.is_(False)).order_by(ParkingSpot.spot_id).limit(1)
    ).first()


def _log_detection(
    db: Session,
    plate: str,
    confidence: float,
    camera: CameraSource,
    accepted: bool,
    reason: str,
    spot_id: int | None = None,
) -> None:
    db.add(
        DetectionLog(
            spot_id=spot_id,
            license_plate=plate,
            confidence=confidence,
            event_type=_event_type_for_camera(camera),
            camera_source=camera.value,
            accepted=accepted,
            reason=reason,
        )
    )


def _visit_response(visit: VehicleVisit) -> dict:
    return {
        "session_id": visit.visit_id,
        "license_plate": visit.license_plate,
        "spot_id": visit.spot_id,
        "entry_time": visit.entry_time,
        "exit_time": visit.exit_time,
        "duration_minutes": visit.duration_minutes,
        "fee": visit.fee,
        "amount_paid": visit.amount_paid,
        "paid_at": visit.paid_at,
        "status": visit.status.value,
    }


@app.get("/")
def home(db: Session = Depends(get_db)):
    occupied = _occupied_count(db)
    return {
        "status": "Smart Parking API is Online",
        "system_time": datetime.now(),
        "total_spots": TOTAL_SPOTS,
        "available_spots": TOTAL_SPOTS - occupied,
    }


@app.get("/api/spots")
def get_availability(db: Session = Depends(get_db)):
    occupied = _occupied_count(db)
    return {
        "total_spots": TOTAL_SPOTS,
        "occupied": occupied,
        "available": TOTAL_SPOTS - occupied,
        "updated_at": datetime.now(),
    }


@app.post("/api/entry")
def vehicle_entry(data: PlateDetectionRequest, db: Session = Depends(get_db)):
    plate = _normalize_plate(data.license_plate)

    if data.camera_source != CameraSource.ENTRY:
        _log_detection(db, plate, data.confidence, data.camera_source, False, "Wrong camera source for entry")
        db.commit()
        raise HTTPException(status_code=400, detail="Entry endpoint requires camera_source='entry'.")

    if data.confidence < MIN_OCR_CONFIDENCE:
        _log_detection(db, plate, data.confidence, CameraSource.ENTRY, False, "Low OCR confidence")
        db.commit()
        raise HTTPException(status_code=400, detail="OCR confidence too low. Please retry.")

    if _find_active_visit(db, plate):
        _log_detection(db, plate, data.confidence, CameraSource.ENTRY, False, "Duplicate entry")
        db.commit()
        raise HTTPException(status_code=409, detail=f"Vehicle {plate} already has an active session.")

    spot = _get_open_spot(db)
    if not spot:
        _log_detection(db, plate, data.confidence, CameraSource.ENTRY, False, "Lot full")
        db.commit()
        raise HTTPException(status_code=409, detail="Parking lot is full. No available spots.")

    now = datetime.now()
    spot.is_occupied = True
    spot.current_plate = plate
    spot.updated_at = now

    visit = VehicleVisit(
        license_plate=plate,
        spot_id=spot.spot_id,
        entry_time=now,
        status=VisitStatus.ACTIVE,
    )
    db.add(visit)
    db.flush()
    _log_detection(db, plate, data.confidence, CameraSource.ENTRY, True, "Entry recorded", spot.spot_id)
    db.commit()
    db.refresh(visit)

    return {
        "message": "Entry recorded. Gate open.",
        "session_id": visit.visit_id,
        "license_plate": visit.license_plate,
        "spot_id": visit.spot_id,
        "entry_time": visit.entry_time,
        "available_spots": TOTAL_SPOTS - _occupied_count(db),
    }


@app.post("/api/exit")
def vehicle_exit(data: PlateDetectionRequest, db: Session = Depends(get_db)):
    plate = _normalize_plate(data.license_plate)

    if data.camera_source != CameraSource.EXIT:
        _log_detection(db, plate, data.confidence, data.camera_source, False, "Wrong camera source for exit")
        db.commit()
        raise HTTPException(status_code=400, detail="Exit endpoint requires camera_source='exit'.")

    if data.confidence < MIN_OCR_CONFIDENCE:
        _log_detection(db, plate, data.confidence, CameraSource.EXIT, False, "Low OCR confidence")
        db.commit()
        raise HTTPException(status_code=400, detail="OCR confidence too low. Please retry.")

    visit = _find_active_visit(db, plate)
    if not visit:
        _log_detection(db, plate, data.confidence, CameraSource.EXIT, False, "No active session")
        db.commit()
        raise HTTPException(status_code=404, detail=f"No active parking session found for plate {plate}.")

    now = datetime.now()
    duration_minutes = round((now - visit.entry_time).total_seconds() / 60, 1)
    fee = _calculate_fee(visit.entry_time, now)

    visit.exit_time = now
    visit.duration_minutes = duration_minutes
    visit.fee = fee
    visit.status = VisitStatus.EXITED

    spot = db.get(ParkingSpot, visit.spot_id)
    if spot:
        spot.is_occupied = False
        spot.current_plate = None
        spot.updated_at = now

    _log_detection(db, plate, data.confidence, CameraSource.EXIT, True, "Exit recorded", visit.spot_id)
    db.commit()
    db.refresh(visit)

    return {
        "message": "Exit recorded. Please proceed to payment.",
        **_visit_response(visit),
        "available_spots": TOTAL_SPOTS - _occupied_count(db),
    }


@app.post("/api/payment/{session_id}")
def process_payment(session_id: int, payment: PaymentRequest, db: Session = Depends(get_db)):
    visit = db.get(VehicleVisit, session_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Session not found.")

    if visit.status == VisitStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Vehicle has not exited yet.")
    if visit.status == VisitStatus.PAID:
        raise HTTPException(status_code=400, detail="Session already paid.")
    if visit.fee is None:
        raise HTTPException(status_code=400, detail="Fee has not been calculated.")
    if payment.amount < visit.fee:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient payment. Required: ${visit.fee}, received: ${payment.amount}",
        )

    visit.status = VisitStatus.PAID
    visit.amount_paid = payment.amount
    visit.paid_at = datetime.now()
    db.commit()
    db.refresh(visit)

    return {
        "message": "Payment accepted. Gate open.",
        "session_id": visit.visit_id,
        "license_plate": visit.license_plate,
        "fee_charged": visit.fee,
        "amount_paid": visit.amount_paid,
        "paid_at": visit.paid_at,
    }


@app.get("/api/sessions/active")
def get_active_sessions(db: Session = Depends(get_db)):
    active = db.scalars(
        select(VehicleVisit).where(VehicleVisit.status == VisitStatus.ACTIVE).order_by(VehicleVisit.entry_time)
    ).all()
    return {
        "count": len(active),
        "sessions": [_visit_response(visit) for visit in active],
    }


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    visit = db.get(VehicleVisit, session_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _visit_response(visit)


@app.get("/api/events")
def get_plate_events(limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    events = db.scalars(select(DetectionLog).order_by(DetectionLog.detected_at.desc()).limit(limit)).all()
    return {
        "total_events": db.scalar(select(func.count()).select_from(DetectionLog)) or 0,
        "events": [
            {
                "event_id": event.log_id,
                "spot_id": event.spot_id,
                "license_plate": event.license_plate,
                "confidence": event.confidence,
                "event_type": event.event_type.value,
                "camera_source": event.camera_source,
                "accepted": event.accepted,
                "reason": event.reason,
                "timestamp": event.detected_at,
            }
            for event in events
        ],
    }


@app.get("/api/analytics/daily")
def daily_analytics(db: Session = Depends(get_db)):
    today = datetime.now().date()
    visits = db.scalars(select(VehicleVisit)).all()
    todays_visits = [visit for visit in visits if visit.entry_time.date() == today]

    total_revenue = sum(visit.fee or 0 for visit in todays_visits if visit.status == VisitStatus.PAID)
    hour_counts: dict[int, int] = {}
    plate_counts: dict[str, int] = {}

    for visit in todays_visits:
        hour_counts[visit.entry_time.hour] = hour_counts.get(visit.entry_time.hour, 0) + 1
        plate_counts[visit.license_plate] = plate_counts.get(visit.license_plate, 0) + 1

    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None
    repeat_vehicles = [plate for plate, count in plate_counts.items() if count > 1]

    return {
        "date": str(today),
        "total_revenue": round(total_revenue, 2),
        "vehicles_served": len(todays_visits),
        "currently_parked": sum(1 for visit in todays_visits if visit.status == VisitStatus.ACTIVE),
        "peak_hour": f"{peak_hour}:00" if peak_hour is not None else "N/A",
        "repeat_vehicles": repeat_vehicles,
    }
