from datetime import datetime
from enum import Enum as PyEnum
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./parking_demo.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


class VisitStatus(PyEnum):
    ACTIVE = "ACTIVE"
    EXITED = "EXITED"
    PAID = "PAID"


class DetectionEvent(PyEnum):
    ENTRY_SCAN = "entry_scan"
    EXIT_SCAN = "exit_scan"
    RESCAN = "rescan"


class ParkingSpot(Base):
    __tablename__ = "parking_spots"

    spot_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_occupied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_plate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    visits: Mapped[list["VehicleVisit"]] = relationship(back_populates="spot")
    detections: Mapped[list["DetectionLog"]] = relationship(back_populates="spot")


class VehicleVisit(Base):
    __tablename__ = "vehicle_visits"

    visit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("parking_spots.spot_id"), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[VisitStatus] = mapped_column(Enum(VisitStatus), default=VisitStatus.ACTIVE, nullable=False)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    spot: Mapped["ParkingSpot"] = relationship(back_populates="visits")


class DetectionLog(Base):
    __tablename__ = "detection_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spot_id: Mapped[int | None] = mapped_column(ForeignKey("parking_spots.spot_id"), nullable=True)
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    event_type: Mapped[DetectionEvent] = mapped_column(Enum(DetectionEvent), nullable=False)
    camera_source: Mapped[str] = mapped_column(String(20), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    spot: Mapped["ParkingSpot"] = relationship(back_populates="detections")


def init_db(total_spots: int = 50) -> None:
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        existing_ids = set(db.scalars(select(ParkingSpot.spot_id)).all())
        for spot_id in range(1, total_spots + 1):
            if spot_id not in existing_ids:
                db.add(ParkingSpot(spot_id=spot_id))
        db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="Smart Parking Database")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def database_status():
    return {
        "status": "Database models initialized",
        "database_url": DATABASE_URL,
    }
