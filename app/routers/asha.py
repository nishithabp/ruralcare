import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require
from ..models import PatientMedicine, SymptomReport, User

router = APIRouter(prefix="/asha", tags=["asha"])
asha_only = require("asha")


def _my_patient_ids(db: Session, asha: User) -> list[int]:
    return list(db.scalars(select(User.id).where(User.role == "patient", User.asha_id == asha.id)))


@router.get("/patients")
def patients(db: Session = Depends(get_db), asha: User = Depends(asha_only)):
    out = []
    for p in db.scalars(select(User).where(User.role == "patient", User.asha_id == asha.id)):
        last = db.scalar(select(SymptomReport).where(SymptomReport.patient_id == p.id).order_by(SymptomReport.id.desc()))
        out.append({"id": p.id, "name": p.name, "village": p.village, "condition": p.condition, "phone": p.phone,
                    "latest_symptoms": last.symptoms if last else [], "urgent": bool(last and last.urgent)})
    return out


@router.get("/alerts")
def alerts(db: Session = Depends(get_db), asha: User = Depends(asha_only)):
    """Open symptom reports of my patients, and medicines that expire within 7 days."""
    ids = _my_patient_ids(db, asha)
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    out = []
    if ids:
        for r in db.scalars(select(SymptomReport).where(SymptomReport.patient_id.in_(ids), SymptomReport.visited.is_(False))
                            .order_by(SymptomReport.urgent.desc(), SymptomReport.id.desc())):
            out.append({"kind": "symptoms", "id": r.id, "patient_id": r.patient_id, "patient": names[r.patient_id],
                        "symptoms": r.symptoms, "level": "bad" if r.urgent else "warn", "created_at": r.created_at})
        today = dt.date.today()
        for m in db.scalars(select(PatientMedicine).where(PatientMedicine.patient_id.in_(ids))):
            days = (m.expiry - today).days
            if days <= 7:
                out.append({"kind": "expiring", "patient_id": m.patient_id, "patient": names[m.patient_id],
                            "medicine": f"{m.name} {m.strength}", "days": days, "level": "warn"})
    return out


@router.post("/alerts/{report_id}/visit")
def mark_visited(report_id: int, db: Session = Depends(get_db), asha: User = Depends(asha_only)):
    r = db.get(SymptomReport, report_id)
    if not r or r.patient_id not in _my_patient_ids(db, asha):
        raise HTTPException(404, "not_found")
    r.visited = True
    db.commit()
    return {"id": r.id, "visited": True}
