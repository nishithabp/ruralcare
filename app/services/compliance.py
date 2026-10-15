"""Pharmacy compliance scoring for the drug-control dashboard."""
import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Batch, Report, ScanLog, User


def level(score: int) -> str:
    return "ok" if score >= 75 else "watch" if score >= 50 else "inspect"


def pharmacy_scores(db: Session) -> list[dict]:
    today = dt.date.today()
    rows = []
    for ph in db.scalars(select(User).where(User.role == "pharmacy", User.is_active.is_(True))):
        total = db.scalar(select(func.count(Batch.id)).where(Batch.pharmacy_id == ph.id)) or 0
        expired_stock = db.scalar(select(func.count(Batch.id)).where(
            Batch.pharmacy_id == ph.id, Batch.expiry < today, Batch.quantity > 0)) or 0
        flagged_scans = db.scalar(
            select(func.count(ScanLog.id)).join(Batch, Batch.id == ScanLog.batch_id)
            .where(Batch.pharmacy_id == ph.id, ScanLog.status.in_(("suspicious", "expired")))) or 0
        reports = db.scalar(select(func.count(Report.id)).where(Report.pharmacy_id == ph.id)) or 0

        score = 100 - min(40, expired_stock * 20) - min(30, flagged_scans * 3) - min(30, reports * 10)
        score = max(0, score)
        notes = []
        if expired_stock:
            notes.append("expired_stock")
        if flagged_scans:
            notes.append("flagged_scans")
        if reports:
            notes.append("public_reports")
        rows.append({"id": ph.id, "name": ph.name, "village": ph.village, "lat": ph.lat, "lng": ph.lng,
                     "batches": total, "expired_stock": expired_stock, "flagged_scans": flagged_scans,
                     "reports": reports, "score": score, "level": level(score), "notes": notes or ["none"]})
    return sorted(rows, key=lambda r: r["score"])
