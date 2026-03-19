// Demian
from datetime import datetime
from enum import Enum as PyEnum

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import (
    create_engine,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session, relationship

DATABASE_URL = " "

engine = create_engine(DATABASE_URL, echo=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class VisitStatus(PyEnum):
    PARKED = "parked"
    EXITED = "exited"


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
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    visits: Mapped[list["VehicleVisit"]] = relationship(back_populates="spot")
    detections: Mapped[list["DetectionLog"]] = relationship(back_populates="spot")


class VehicleVisit(Base):
    __tablename__ = "vehicle_visits"

    visit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("parking_spots.spot_id"), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[VisitStatus] = mapped_column(Enum(VisitStatus), default=VisitStatus.PARKED, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee: Mapped[float | None] = mapped_column(Float, nullable=True)

    spot: Mapped["ParkingSpot"] = relationship(back_populates="visits")


class DetectionLog(Base):
    __tablename__ = "detection_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("parking_spots.spot_id"), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    event_type: Mapped[DetectionEvent] = mapped_column(Enum(DetectionEvent), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    spot: Mapped["ParkingSpot"] = relationship(back_populates="detections")


Base.metadata.create_all(engine)


app = FastAPI()


class ParkingDetection(BaseModel):
    spot_id: int
    license_plate: str
    confidence: float
    event_type: str  # entry_scan, exit_scan, rescan


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
