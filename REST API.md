# Smart Parking Management System REST API

> **Framework:** FastAPI · **Persistence:** SQLAlchemy models in `database.py` · **Default local DB:** SQLite · **Configured DB:** MySQL via `DATABASE_URL`

The backend is independent of display hardware. Raspberry Pi, Arduino, or OCR camera clients can call the API over HTTP.

---

## Quick Start

```bash
pip install -r requirements.txt
uvicorn REST_API:app --reload
```

Interactive docs are available at:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

If no `.env` file is present, the API uses a local SQLite file named `parking_demo.db`. To use MySQL, copy `.env.example` to `.env` and update `DATABASE_URL`.

---

## Endpoints Overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check & system time |
| `GET` | `/api/spots` | Real-time parking availability |
| `POST` | `/api/entry` | Record vehicle entry from the entry camera |
| `POST` | `/api/exit` | Record vehicle exit and compute fee |
| `POST` | `/api/payment/{session_id}` | Confirm manual payment and mark session PAID |
| `GET` | `/api/sessions/active` | List all currently parked vehicles |
| `GET` | `/api/sessions/{session_id}` | Look up one parking session |
| `GET` | `/api/events` | OCR plate-detection event log |
| `GET` | `/api/analytics/daily` | Daily revenue, peak hour, repeat vehicles |

`session_id` maps to `vehicle_visits.visit_id` in the database.

---

## Data Model

`REST_API.py` now uses the SQLAlchemy models from `database.py`.

| Table | Purpose |
|-------|---------|
| `parking_spots` | Spot occupancy state and currently parked plate |
| `vehicle_visits` | Entry/exit/payment lifecycle for each vehicle visit |
| `detection_logs` | OCR scan audit log for accepted and rejected reads |

### Session State Machine

```text
ACTIVE --(exit camera)--> EXITED --(payment)--> PAID
```

- **ACTIVE**: Vehicle is currently parked.
- **EXITED**: Vehicle has left; duration and fee have been calculated.
- **PAID**: Manual payment has been recorded.

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

1. Normalize the plate string to uppercase.
2. Reject if `camera_source` is not `entry`.
3. Reject if OCR confidence is below `0.6`.
4. Reject if the same plate already has an ACTIVE visit.
5. Find the first open parking spot.
6. Create a `vehicle_visits` row with status `ACTIVE`.
7. Mark the assigned `parking_spots` row occupied.
8. Add a `detection_logs` row.

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

1. Normalize the plate string to uppercase.
2. Reject if `camera_source` is not `exit`.
3. Reject if OCR confidence is below `0.6`.
4. Reject if there is no ACTIVE visit for the plate.
5. Calculate duration and fee.
6. Update the `vehicle_visits` row to `EXITED`.
7. Mark the related `parking_spots` row open.
8. Add a `detection_logs` row.

Fee calculation uses `$2.50/hour` with a minimum 30-minute charge.

---

## Payment (`POST /api/payment/{session_id}`)

**Request body:**

```json
{
  "amount": 5.00
}
```

Transitions the session from `EXITED` to `PAID`.

Rejects when:

| Scenario | API Response |
|----------|--------------|
| Session does not exist | `404` |
| Vehicle has not exited | `400` |
| Session is already paid | `400` |
| Payment amount is below fee | `400` |

---

## Edge Cases Handled

| Scenario | API Response |
|----------|--------------|
| Low OCR confidence | `400` |
| Wrong camera source for endpoint | `400` |
| Parking lot full | `409` |
| Duplicate active entry | `409` |
| Exit without active session | `404` |
| Insufficient payment | `400` |
| Double payment | `400` |

All accepted and rejected OCR scans are stored in `detection_logs`.

---

## Analytics (`GET /api/analytics/daily`)

Returns:

- Total paid revenue for today
- Vehicles served today
- Currently parked count
- Peak entry hour
- Repeat vehicle plates

---

## Notes

- `parking_spots` are seeded automatically on application startup.
- Without `.env`, the app uses `sqlite:///./parking_demo.db` for local testing.
- With `.env`, the app uses the configured `DATABASE_URL`, such as MySQL through PyMySQL.
