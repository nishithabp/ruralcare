"""Medicine authenticity check: registry lookup, expiry, duplicate-scan detection."""
import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Batch, ScanLog, User
from ..schemas import BatchPublic, VerifyOut


def verify_code(db: Session, code: str, user_id: int | None = None,
                lat: float | None = None, lng: float | None = None) -> VerifyOut:
    s = get_settings()
    code = code.strip().upper()
    batch = db.scalar(select(Batch).where(Batch.code == code))

    if batch is None:
        status, reason, count = "suspicious", "not_registered", None
    else:
        # atomic increment so concurrent scans are all counted
        db.execute(update(Batch).where(Batch.id == batch.id).values(scan_count=Batch.scan_count + 1))
        db.refresh(batch)
        count = batch.scan_count
        if batch.expiry < dt.date.today():
            status, reason = "expired", "past_expiry"
        elif count > s.max_scans_before_flag:
            status, reason = "suspicious", "duplicate_scans"
        else:
            status, reason = "genuine", "ok"

    db.add(ScanLog(user_id=user_id, code=code, batch_id=batch.id if batch else None,
                   status=status, reason=reason, lat=lat, lng=lng))
    db.commit()

    public = None
    if batch:
        pharmacy = db.get(User, batch.pharmacy_id)
        public = BatchPublic(medicine_name=batch.medicine_name, strength=batch.strength,
                             manufacturer=batch.manufacturer, batch_no=batch.batch_no,
                             expiry=batch.expiry, registered_by=pharmacy.name if pharmacy else "")
    return VerifyOut(status=status, reason=reason, code=code, scan_count=count, batch=public)
