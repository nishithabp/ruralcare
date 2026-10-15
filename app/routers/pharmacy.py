import io

import segno
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require
from ..models import Batch, User
from ..schemas import BatchIn, BatchOut

router = APIRouter(prefix="/pharmacy", tags=["pharmacy"])


def _own_batch(db: Session, batch_id: int, user: User) -> Batch:
    b = db.get(Batch, batch_id)
    if not b or b.pharmacy_id != user.id:
        raise HTTPException(404, "batch_not_found")
    return b


@router.post("/batches", response_model=BatchOut, status_code=201)
def register_batch(data: BatchIn, db: Session = Depends(get_db), user: User = Depends(require("pharmacy"))):
    """The pharmacy enters the medicine details itself; patients see exactly these when they scan the code."""
    b = Batch(**data.model_dump(), pharmacy_id=user.id)
    db.add(b)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "code_already_registered")
    return b


@router.get("/batches", response_model=list[BatchOut])
def my_batches(db: Session = Depends(get_db), user: User = Depends(require("pharmacy"))):
    return db.scalars(select(Batch).where(Batch.pharmacy_id == user.id).order_by(Batch.id.desc())).all()


@router.delete("/batches/{batch_id}", status_code=204)
def remove_batch(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require("pharmacy"))):
    db.delete(_own_batch(db, batch_id, user))
    db.commit()


@router.get("/batches/{batch_id}/qr.png")
def qr_png(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require("pharmacy"))):
    b = _own_batch(db, batch_id, user)
    buf = io.BytesIO()
    segno.make(b.code, error="m", micro=False).save(buf, kind="png", scale=8, border=4)
    return Response(buf.getvalue(), media_type="image/png")


@router.get("/batches/{batch_id}/qr.svg")
def qr_svg(batch_id: int, db: Session = Depends(get_db), user: User = Depends(require("pharmacy"))):
    b = _own_batch(db, batch_id, user)
    buf = io.BytesIO()
    segno.make(b.code, error="m", micro=False).save(buf, kind="svg", scale=8, border=4)
    return Response(buf.getvalue(), media_type="image/svg+xml")
