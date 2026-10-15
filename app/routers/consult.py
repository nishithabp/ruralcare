import io
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import current_user, require
from ..models import Consultation, Message, PatientMedicine, Prescription, User, utcnow
from ..schemas import (ConsultIn, ConsultOut, DoctorOut, MessageIn, MessageOut, PrescriptionIn, PrescriptionOut,
                       UserOut)
from .calls import hub

router = APIRouter(tags=["consultation"])


def _consult_for(db: Session, cid: int, user: User) -> Consultation:
    c = db.get(Consultation, cid)
    if not c or user.id not in (c.patient_id, c.doctor_id):
        raise HTTPException(404, "consultation_not_found")
    return c


def _msg_out(m: Message) -> MessageOut:
    return MessageOut(id=m.id, sender_id=m.sender_id, body=m.body, has_photo=bool(m.photo_path), created_at=m.created_at)


@router.get("/doctors", response_model=list[DoctorOut])
def doctors(db: Session = Depends(get_db), _=Depends(current_user)):
    """`online` is true while the doctor has the app open and can receive calls."""
    docs = db.scalars(select(User).where(User.role == "doctor", User.is_active.is_(True))).all()
    return [DoctorOut(**UserOut.model_validate(d).model_dump(), online=d.id in hub.sockets and d.id not in hub.active)
            for d in docs]


@router.post("/consultations", response_model=ConsultOut, status_code=201)
def request_consultation(data: ConsultIn, db: Session = Depends(get_db), user: User = Depends(require("patient"))):
    """Starts a text-and-photo consultation (low-bandwidth, asynchronous). Calls start through /ws."""
    doc = db.get(User, data.doctor_id)
    if not doc or doc.role != "doctor":
        raise HTTPException(404, "doctor_not_found")
    c = Consultation(patient_id=user.id, doctor_id=doc.id, mode=data.mode, status="requested")
    db.add(c)
    db.commit()
    return c


@router.get("/consultations", response_model=list[ConsultOut])
def my_consultations(db: Session = Depends(get_db), user: User = Depends(require("patient", "doctor"))):
    col = Consultation.patient_id if user.role == "patient" else Consultation.doctor_id
    return db.scalars(select(Consultation).where(col == user.id).order_by(Consultation.id.desc()).limit(100)).all()


@router.post("/consultations/{cid}/end", response_model=ConsultOut)
def end_consultation(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _consult_for(db, cid, user)
    if c.status in ("requested", "connected", "ringing"):
        c.status, c.ended_at = "ended", utcnow()
        db.commit()
    return c


# ---------- messages (text and compressed photos) ----------
@router.get("/consultations/{cid}/messages", response_model=list[MessageOut])
def messages(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _consult_for(db, cid, user)
    return [_msg_out(m) for m in db.scalars(select(Message).where(Message.consultation_id == cid).order_by(Message.id))]


@router.post("/consultations/{cid}/messages", response_model=MessageOut, status_code=201)
def send_message(cid: int, data: MessageIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _consult_for(db, cid, user)
    m = Message(consultation_id=cid, sender_id=user.id, body=data.body)
    db.add(m)
    db.commit()
    return _msg_out(m)


@router.post("/consultations/{cid}/photo", response_model=MessageOut, status_code=201)
async def send_photo(cid: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    """Photos are shrunk to roughly 40 KB so they upload on weak networks."""
    _consult_for(db, cid, user)
    raw = await file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "image_too_large")
    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "not_an_image")
    img.thumbnail((800, 800))
    buf = io.BytesIO()
    for quality in (60, 45, 30):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= 40 * 1024:
            break
    folder = os.path.join(get_settings().upload_dir, "consultations", str(cid))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex}.jpg")
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    m = Message(consultation_id=cid, sender_id=user.id, body="", photo_path=path)
    db.add(m)
    db.commit()
    return _msg_out(m)


@router.get("/messages/{mid}/photo")
def message_photo(mid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(Message, mid)
    if not m or not m.photo_path:
        raise HTTPException(404, "not_found")
    _consult_for(db, m.consultation_id, user)
    return FileResponse(m.photo_path, media_type="image/jpeg")


# ---------- doctor ----------
@router.get("/doctor/queue")
def doctor_queue(db: Session = Depends(get_db), user: User = Depends(require("doctor"))):
    """Consultations waiting for a prescription."""
    out = []
    cons = db.scalars(select(Consultation).where(
        Consultation.doctor_id == user.id,
        or_(Consultation.status == "requested", Consultation.status == "ended"))
        .order_by(Consultation.id.desc()).limit(100))
    for c in cons:
        if db.scalar(select(Prescription.id).where(Prescription.consultation_id == c.id)):
            continue
        p = db.get(User, c.patient_id)
        out.append({"consultation_id": c.id, "patient_id": p.id, "patient": p.name, "condition": p.condition,
                    "mode": c.mode, "status": c.status, "created_at": c.created_at})
    return out


@router.get("/doctor/patients/{patient_id}/record")
def patient_record(patient_id: int, db: Session = Depends(get_db), user: User = Depends(require("doctor"))):
    """A doctor can open the record of patients they have a consultation with."""
    has = db.scalar(select(Consultation.id).where(Consultation.doctor_id == user.id,
                                                  Consultation.patient_id == patient_id).limit(1))
    if not has:
        raise HTTPException(403, "no_consultation_with_patient")
    p = db.get(User, patient_id)
    meds = db.scalars(select(PatientMedicine).where(PatientMedicine.patient_id == patient_id)).all()
    return {"patient": UserOut.model_validate(p),
            "medicines": [{"name": m.name, "strength": m.strength, "expiry": m.expiry} for m in meds]}


@router.post("/prescriptions", response_model=PrescriptionOut, status_code=201)
def write_prescription(data: PrescriptionIn, db: Session = Depends(get_db), user: User = Depends(require("doctor"))):
    if data.consultation_id is not None:
        c = db.get(Consultation, data.consultation_id)
        if not c or c.doctor_id != user.id or c.patient_id != data.patient_id:
            raise HTTPException(404, "consultation_not_found")
    else:
        if not db.scalar(select(Consultation.id).where(Consultation.doctor_id == user.id,
                                                       Consultation.patient_id == data.patient_id).limit(1)):
            raise HTTPException(403, "no_consultation_with_patient")
    rx = Prescription(consultation_id=data.consultation_id, patient_id=data.patient_id,
                      doctor_id=user.id, items=data.items)
    db.add(rx)
    db.commit()
    return rx
