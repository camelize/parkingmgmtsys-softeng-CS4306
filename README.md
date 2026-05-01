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
3. Calculate parking duration and fees
4. Store vehicle visits, parking spot state, and OCR detection logs with SQLAlchemy
5. Generate daily revenue and usage analytics

---

## System Architecture

```
Camera   ->   OpenCV / OCR   ->   Plate String
                                      |
                                FastAPI Backend
                                      |
                            REST_API.py demo endpoints
                                      |
                          database.py SQLAlchemy models
                                      |
                              SQLite / MySQL
                                      |
                              Display Clients
                           (Raspberry Pi / Arduino)
```

### System Flow

| Step | Action | Details |
|------|--------|---------|
| Entry | Capture plate at entry gate | Log vehicle + timestamp, check capacity, open gate, spots -1 |
| API + DB | Route requests and persist data | Track active visits, spot occupancy, and detection history |
| Exit | Capture plate at exit gate | Compute duration & fee, update visit, open gate, spots +1 |
| Payment | Confirm manual payment | Mark completed session as paid in the API demo flow |

### Session State Machine

```
ACTIVE  --(exit camera)-->  EXITED  --(payment)-->  PAID
```

`REST_API.py` now persists visits, spots, payments, and detection logs through the SQLAlchemy models in `database.py`.

---

## Tech Stack

| Component | Technology | Owner |
|-----------|------------|-------|
| Computer Vision & OCR | OpenCV + OCR pipeline | Kim Lay & Jessy Quevedo |
| Database | SQLAlchemy + SQLite/MySQL + PyMySQL | Logan Henry & Inseong Hong |
| Backend / API | FastAPI (Python) | Bumjun Ko & Bunlong Tan |

---

## Repository Files

| File | Purpose |
|------|---------|
| `README.md` | Project overview and setup guide |
| `REST_API.py` | FastAPI demo backend for entry, exit, payment, sessions, events, and analytics |
| `REST API.md` | Detailed endpoint documentation with request/response examples |
| `database.py` | SQLAlchemy models and MySQL connection setup |
| `.env.example` | Example database connection string |
| `requirements.txt` | Python dependency list |
| `.gitignore` | Ignores local `.env`, Python cache files, compiled bytecode, and local SQLite DB |

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Database

For local testing, no setup is required. If `.env` is missing, the app uses `sqlite:///./parking_demo.db`.

To use MySQL, create a local `.env` file from the example:

```bash
cp .env.example .env
```

Update `DATABASE_URL` in `.env` with your MySQL username, password, host, port, and database name:

```env
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/parking_demo
```

Make sure the target MySQL database exists before using a MySQL `DATABASE_URL`.

### 3. Run the REST API

```bash
uvicorn REST_API:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

### 4. Run the Database Model App

```bash
uvicorn database:app --reload
```

This standalone app initializes the same SQLAlchemy tables and reports which database URL is configured.

---

## API Endpoints

The main API lives in `REST_API.py`.

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

See [`REST API.md`](REST%20API.md) for full endpoint documentation.

---

## Database Schema

`database.py` defines three SQLAlchemy tables:

| Table | Purpose |
|-------|---------|
| `parking_spots` | Stores each parking spot, occupancy state, current plate, and last update time |
| `vehicle_visits` | Stores vehicle entry/exit records, visit status, duration, and fee |
| `detection_logs` | Stores OCR scan logs with plate, confidence score, event type, and timestamp |

### Model Overview

| Model | Important Fields |
|-------|------------------|
| `ParkingSpot` | `spot_id`, `is_occupied`, `current_plate`, `updated_at` |
| `VehicleVisit` | `visit_id`, `license_plate`, `spot_id`, `entry_time`, `exit_time`, `status`, `duration_minutes`, `fee`, `amount_paid`, `paid_at` |
| `DetectionLog` | `log_id`, `spot_id`, `license_plate`, `confidence`, `event_type`, `camera_source`, `accepted`, `reason`, `detected_at` |

### Database Enums

| Enum | Values |
|------|--------|
| `VisitStatus` | `ACTIVE`, `EXITED`, `PAID` |
| `DetectionEvent` | `entry_scan`, `exit_scan`, `rescan` |

---

## Reliability & Edge Cases

| Scenario | Handling |
|----------|----------|
| Low OCR confidence (< 0.6) | Reject and request re-capture |
| Parking lot full | Reject entry with 409 |
| Duplicate entry (plate already parked) | Reject with 409 |
| Exit without active session | Reject with 404 |
| Insufficient payment | Reject with 400 |

All OCR events, including accepted and rejected detections, are logged in the database for auditing.

---

## Current Development Status

- `REST_API.py` uses SQLAlchemy sessions and the models from `database.py`.
- `database.py` defines and initializes persistent storage tables.
- `.env.example` documents the required `DATABASE_URL` format.
- `requirements.txt` provides one-command dependency installation.

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, reviewed code |
| `rest-api` | Backend API development |
| `database-setup` | MySQL schema and SQLAlchemy integration |
