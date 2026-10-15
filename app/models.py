import datetime as dt
import enum

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Role(str, enum.Enum):
    patient = "patient"
    doctor = "doctor"
    asha = "asha"
    pharmacy = "pharmacy"
    authority = "authority"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))            # pharmacies: the shop name
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(2), default="en")
    village: Mapped[str | None] = mapped_column(String(120), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    speciality: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    asha_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Batch(Base):
    """A medicine batch registered by a pharmacy. `code` is what the strip's QR/barcode contains."""
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120))
    strength: Mapped[str] = mapped_column(String(40))
    manufacturer: Mapped[str] = mapped_column(String(160))
    batch_no: Mapped[str] = mapped_column(String(60))
    expiry: Mapped[dt.date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    pharmacy_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scan_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class ScanLog(Base):
    __tablename__ = "scan_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20))           # genuine | expired | suspicious
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class PatientMedicine(Base):
    __tablename__ = "patient_medicines"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    strength: Mapped[str] = mapped_column(String(40))
    expiry: Mapped[dt.date] = mapped_column(Date)


class SymptomReport(Base):
    __tablename__ = "symptom_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    symptoms: Mapped[list] = mapped_column(JSON)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    visited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(10))              # chat | audio | video
    # requested | ringing | connected | ended | missed | declined | cancelled
    status: Mapped[str] = mapped_column(String(12), default="requested")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int] = mapped_column(ForeignKey("consultations.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text, default="")
    photo_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    consultation_id: Mapped[int | None] = mapped_column(ForeignKey("consultations.id"), nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Report(Base):
    """Crowd-sourced report of suspicious or expired stock."""
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    medicine_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str] = mapped_column(String(30))            # expired_sold | duplicate_scans | not_registered | other
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pharmacy_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    village: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
