# Smart Parking Management System — REST API

> **Framework:** FastAPI  ·  **Database:** MySQL (pending integration)  ·  **Architecture:** API-first

The backend is independent of display hardware; Raspberry Pi / Arduino will act as API clients for the demo.

---

## Quick Start

```bash
pip install fastapi uvicorn pydantic
uvicorn REST_API:app --reload
```

Interactive docs available at `http://127.0.0.1:8000/docs` (Swagger UI).

---

## Endpoints Overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check & system time |
| `GET` | `/api/spots` | Real-time parking availability |
| `POST` | `/api/entry` | Record vehicle entry (from entry camera) |
| `POST` | `/api/exit` | Record vehicle exit & compute fee (from exit camera) |
| `POST` | `/api/payment/{session_id}` | Confirm manual payment → PAID |
| `GET` | `/api/sessions/active` | List all currently parked vehicles |
| `GET` | `/api/sessions/{session_id}` | Look up a single session |
| `GET` | `/api/events` | OCR plate-detection event log |
| `GET` | `/api/analytics/daily` | Daily revenue, peak hour, repeat vehicles |

---

## Session State Machine

```
ACTIVE  ──(exit camera)──▶  EXITED  ──(payment)──▶  PAID
```

- **ACTIVE** — Vehicle is currently parked.
- **EXITED** — Vehicle has left; duration & fee calculated, awaiting payment.
- **PAID** — Payment received; session closed.

---

## Entry Flow (`POST /api/entry`)

**Request body:**
```json
{
  "license_plate": "ABC1234",
  "confidence": 0.92,
  "camera_source": "entry"
}
```

**What happens:**
1. Reject if OCR confidence < 0.6
2. Reject if lot is full (capacity check)
3. Reject if plate already has an ACTIVE session (duplicate entry)
4. Create session (ACTIVE), decrement available spots
5. Log plate event for auditing

---

## Exit Flow (`POST /api/exit`)

**Request body:**
```json
{
  "license_plate": "ABC1234",
  "confidence": 0.88,
  "camera_source": "exit"
}
```

**What happens:**
1. Reject if OCR confidence < 0.6
2. Reject if no ACTIVE session for this plate
3. Calculate duration & fee (minimum 30-min charge, $2.50/hr)
4. Update session to EXITED, increment available spots
5. Log plate event for auditing

---

## Payment (`POST /api/payment/{session_id}`)

**Request body:**
```json
{
  "amount": 5.00
}
```

Transitions session from EXITED → PAID. Rejects if insufficient amount, already paid, or vehicle hasn't exited yet.

---

## Edge Cases Handled (Reliability)

| Scenario | API Response |
|----------|-------------|
| Low OCR confidence (< 0.6) | `400` — plate unreadable |
| Parking lot full | `409` — no available spots |
| Duplicate entry (plate already ACTIVE) | `409` — session already exists |
| Exit without active session | `404` — no active session found |
| Insufficient payment | `400` — amount too low |
| Double payment | `400` — already paid |

All OCR events (accepted and rejected) are logged in the plate events store for debugging and auditing.

---

## Analytics (`GET /api/analytics/daily`)

Returns daily report including:
- **Total revenue** for today
- **Vehicles served** count
- **Currently parked** count
- **Peak hour** (busiest entry hour)
- **Repeat vehicles** (plates that entered more than once)

---

## Database Sync Status

Currently using **in-memory stores** (Python dicts/lists). The Database team (Logan) will integrate MySQL tables:

- `parking_sessions` — entry/exit records, duration, fee, status
- `plate_events` — every OCR detection event with confidence, camera source, accept/reject reason

All `FIXME` comments in the code mark integration points.

---

## Sources

FastAPI documentation, Pydantic docs, team collaboration.
