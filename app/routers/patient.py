import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import require
from ..models import Batch, PatientMedicine, Prescription, SymptomReport, User
from ..schemas import (RED_FLAGS, AshaOut, PatientMedIn, PatientMedOut, PrescriptionOut, SymptomIn, SymptomOut,
                       SymptomReportOut)
from ..services import messages
from ..services.sms import send_sms

router = APIRouter(prefix="/patient", tags=["patient"])
patient_only = require("patient")


@router.get("/asha", response_model=AshaOut | None)
def my_asha(db: Session = Depends(get_db), user: User = Depends(patient_only)):
    return db.get(User, user.asha_id) if user.asha_id else None


@router.get("/medicines", response_model=list[PatientMedOut])
def my_medicines(db: Session = Depends(get_db), user: User = Depends(patient_only)):
    return db.scalars(select(PatientMedicine).where(PatientMedicine.patient_id == user.id)).all()


@router.post("/medicines", response_model=PatientMedOut, status_code=201)
def add_medicine(data: PatientMedIn, db: Session = Depends(get_db), user: User = Depends(patient_only)):
    """Add a scanned (registered) medicine to the patient's list."""
    b = db.scalar(select(Batch).where(Batch.code == data.code))
    if not b:
        raise HTTPException(404, "code_not_registered")
    if b.expiry < dt.date.today():
        raise HTTPException(400, "batch_expired")
    existing = db.scalar(select(PatientMedicine).where(
        PatientMedicine.patient_id == user.id, PatientMedicine.name == b.medicine_name,
        PatientMedicine.strength == b.strength))
    if existing:
        return existing
    m = PatientMedicine(patient_id=user.id, batch_id=b.id, name=b.medicine_name, strength=b.strength, expiry=b.expiry)
    db.add(m)
    db.commit()
    return m


@router.delete("/medicines/{med_id}", status_code=204)
def remove_medicine(med_id: int, db: Session = Depends(get_db), user: User = Depends(patient_only)):
    m = db.get(PatientMedicine, med_id)
    if not m or m.patient_id != user.id:
        raise HTTPException(404, "not_found")
    db.delete(m)
    db.commit()


@router.get("/alerts")
def my_alerts(db: Session = Depends(get_db), user: User = Depends(patient_only)):
    """Expired and soon-to-expire medicines."""
    limit = get_settings().expiry_warning_days
    today, out = dt.date.today(), []
    for m in db.scalars(select(PatientMedicine).where(PatientMedicine.patient_id == user.id)):
        days = (m.expiry - today).days
        if days < 0:
            out.append({"kind": "expired", "medicine": f"{m.name} {m.strength}", "days": days, "level": "bad"})
        elif days <= limit:
            out.append({"kind": "expiring", "medicine": f"{m.name} {m.strength}", "days": days, "level": "warn"})
    return out


@router.post("/symptoms", response_model=SymptomOut, status_code=201)
def report_symptoms(data: SymptomIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                    user: User = Depends(patient_only)):
    """Red-flag symptoms mark the report urgent and SMS the patient's ASHA worker."""
    symptoms = sorted(set(data.symptoms))
    urgent = bool(RED_FLAGS & set(symptoms))
    r = SymptomReport(patient_id=user.id, symptoms=symptoms, urgent=urgent)
    db.add(r)
    db.commit()
    if urgent and user.asha_id:
        asha = db.get(User, user.asha_id)
        if asha:
            bg.add_task(send_sms, asha.phone, messages.render(
                "urgent_asha", asha.language, name=user.name, symptoms=", ".join(symptoms)))
    return SymptomOut(id=r.id, urgent=urgent, message_key="symUrgent" if urgent else "symOk")


@router.get("/symptoms", response_model=list[SymptomReportOut])
def my_symptoms(db: Session = Depends(get_db), user: User = Depends(patient_only)):
    return db.scalars(select(SymptomReport).where(SymptomReport.patient_id == user.id)
                      .order_by(SymptomReport.id.desc()).limit(50)).all()


@router.get("/prescriptions", response_model=list[PrescriptionOut])
def my_prescriptions(db: Session = Depends(get_db), user: User = Depends(patient_only)):
    return db.scalars(select(Prescription).where(Prescription.patient_id == user.id)
                      .order_by(Prescription.id.desc())).all()
