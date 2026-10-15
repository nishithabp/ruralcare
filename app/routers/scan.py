from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user, require
from ..models import Batch, Report, ScanLog, User
from ..schemas import ReportIn, ReportOut, ScanOut, VerifyIn, VerifyOut
from ..services.imagecode import decode_image
from ..services.verify import verify_code

router = APIRouter(tags=["scan"])
MAX_UPLOAD = 5 * 1024 * 1024


@router.post("/scan/verify", response_model=VerifyOut)
def verify(data: VerifyIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Check a code that was read on the phone or typed by hand."""
    return verify_code(db, data.code, user.id, data.lat, data.lng)


@router.post("/scan/image", response_model=VerifyOut)
async def verify_image(file: UploadFile = File(...), lat: float | None = None, lng: float | None = None,
                       db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Photo of a QR code or barcode: the server reads it and verifies it."""
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image_too_large")
    try:
        code = decode_image(data)
    except ValueError:
        raise HTTPException(415, "not_an_image")
    if not code:
        raise HTTPException(422, "no_code_found")
    return verify_code(db, code[:64], user.id, lat, lng)


@router.get("/scan/history", response_model=list[ScanOut])
def history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(select(ScanLog, Batch).outerjoin(Batch, Batch.id == ScanLog.batch_id)
                      .where(ScanLog.user_id == user.id).order_by(ScanLog.id.desc()).limit(50))
    return [ScanOut(id=s.id, code=s.code, status=s.status, reason=s.reason, created_at=s.created_at,
                    medicine_name=b.medicine_name if b else None, strength=b.strength if b else None)
            for s, b in rows]


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(data: ReportIn, db: Session = Depends(get_db), user: User = Depends(require("patient", "asha"))):
    """Crowd-sourced report of suspicious or expired stock."""
    pharmacy_id, name = None, data.medicine_name
    if data.code:
        b = db.scalar(select(Batch).where(Batch.code == data.code.strip().upper()))
        if b:
            pharmacy_id, name = b.pharmacy_id, name or f"{b.medicine_name} {b.strength}"
    r = Report(reporter_id=user.id, code=data.code.strip().upper() if data.code else None, medicine_name=name,
               reason=data.reason, note=data.note, pharmacy_id=pharmacy_id,
               village=data.village or user.village, lat=data.lat, lng=data.lng)
    db.add(r)
    db.commit()
    return r
