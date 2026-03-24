# Smart Parking Management System

> Automated Entry and Exit Monitoring via License Plate Recognition

**Course:** Software Engineering — CS-4306-020, ASU

---

## Problem

Parking lots often rely on manual tracking, leading to:
- Entry/exit delays and recording errors
- No real-time visibility into available spots for drivers and staff
- Time-consuming and inconsistent fee calculation and daily reporting

## Project Goal

Build an **API-first** smart parking system using license plate recognition to:
1. Automatically log entry/exit time per vehicle
2. Update available spots in real time
3. Calculate parking duration and fees (payment handled manually)
4. Generate daily revenue and usage analytics (peak times, repeat vehicles)

---

## System Architecture

```
Camera  →  OpenCV  →  Tesseract OCR  →  Plate String
                                             │
                                       POST /api/entry
                                       POST /api/exit
                                             │
                                          FastAPI  ←→  MySQL
                                             │
                                     Display Clients
                                  (Raspberry Pi / Arduino)
```

### System Flow

| Step | Action | Details |
|------|--------|---------|
| **Entry** | Capture plate at entry gate | Log vehicle + timestamp, check capacity, open gate, spots −1 |
| **API + DB** | Route requests | Store records, track active vehicles, update availability |
| **Exit** | Capture plate at exit gate | Compute duration & fee, manual payment, open gate, spots +1 |

### Session State Machine

```
ACTIVE  ──(exit camera)──▶  EXITED  ──(payment)──▶  PAID
```

---

## Tech Stack

| Component | Technology | Owner |
|-----------|------------|-------|
| Computer Vision & OCR | OpenCV + EasyOCR | Kim Lay & Jessy Quevedo |
| Database | MySQL + SQLAlchemy | Logan Henry & Inseong Hong |
| Backend / API | FastAPI (Python) | Bumjun Ko & Bunlong Tan |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check & system status |
| `GET` | `/api/spots` | Real-time parking availability |
| `POST` | `/api/entry` | Record vehicle entry |
| `POST` | `/api/exit` | Record vehicle exit & compute fee |
| `POST` | `/api/payment/{session_id}` | Confirm manual payment |
| `GET` | `/api/sessions/active` | List currently parked vehicles |
| `GET` | `/api/sessions/{session_id}` | Look up a single session |
| `GET` | `/api/events` | OCR plate-detection event log |
| `GET` | `/api/analytics/daily` | Daily revenue & usage report |

See [`REST API.md`](REST%20API.md) for full endpoint documentation with request/response examples.

---

## Quick Start

```bash
# Install dependencies
pip install fastapi uvicorn pydantic

# Run the server
uvicorn REST_API:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

---

## Project Structure

```
├── README.md           ← You are here
├── REST_API.py         ← FastAPI backend (entry/exit/payment/analytics)
├── REST API.md         ← API endpoint documentation
└── opencv_notes.py     ← OpenCV + OCR pipeline notes
```

---

## Reliability & Edge Cases

| Scenario | Handling |
|----------|----------|
| Low OCR confidence (< 0.6) | Reject and request re-capture |
| Parking lot full | Reject entry with 409 |
| Duplicate entry (plate already parked) | Reject with 409 |
| Exit without active session | Reject with 404 |
| Insufficient payment | Reject with 400 |

All OCR events (accepted and rejected) are logged in the plate events store for auditing.

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, reviewed code |
| `rest-api` | Backend API development |
| `database-design` | MySQL schema and integration |

---

## Data Storage

Currently using **in-memory stores** for development. The Database team will integrate MySQL with two main tables:

- **`parking_sessions`** — entry/exit records, duration, fee, session status
- **`plate_events`** — every OCR detection event with confidence, camera source, accept/reject reason
