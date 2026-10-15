from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require
from ..models import Batch, Report
from ..schemas import ReportOut
from ..services.compliance import pharmacy_scores

router = APIRouter(prefix="/authority", tags=["drug authority"])
authority_only = require("authority")


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(authority_only)):
    pharmacies = pharmacy_scores(db)
    return {
        "pharmacies_tracked": len(pharmacies),
        "batches_registered": db.scalar(select(func.count(Batch.id))) or 0,
        "need_inspection": sum(1 for p in pharmacies if p["level"] == "inspect"),
        "public_reports": db.scalar(select(func.count(Report.id))) or 0,
        "pharmacies": pharmacies,   # includes lat/lng for the heatmap
    }


@router.get("/pharmacies")
def pharmacies(db: Session = Depends(get_db), _=Depends(authority_only)):
    return pharmacy_scores(db)


@router.get("/reports", response_model=list[ReportOut])
def reports(limit: int = 100, db: Session = Depends(get_db), _=Depends(authority_only)):
    return db.scalars(select(Report).order_by(Report.id.desc()).limit(min(limit, 500))).all()
