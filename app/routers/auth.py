from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user, require
from ..models import User
from ..schemas import AdminUserIn, RegisterIn, TokenOut, UserOut, UserPatch
from ..security import create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


def _assign_asha(db: Session, village: str | None) -> int | None:
    if not village:
        return None
    return db.scalar(select(User.id).where(User.role == "asha", User.village == village).limit(1))


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    """Public sign-up creates a patient. Other roles are created by the drug authority."""
    if db.scalar(select(User).where(User.phone == data.phone)):
        raise HTTPException(409, "phone_taken")
    user = User(role="patient", name=data.name, phone=data.phone, password_hash=hash_password(data.password),
                language=data.language, village=data.village, condition=data.condition,
                lat=data.lat, lng=data.lng, asha_id=_assign_asha(db, data.village))
    db.add(user)
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """`username` is the phone number."""
    user = db.scalar(select(User).where(User.phone == form.username))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "invalid_credentials")
    return TokenOut(access_token=create_token(user.id, user.role), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/auth/me", response_model=UserOut)
def update_me(patch: UserPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in patch.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    return user


@router.post("/admin/users", response_model=UserOut, status_code=201)
def admin_create_user(data: AdminUserIn, db: Session = Depends(get_db), _=Depends(require("authority"))):
    if db.scalar(select(User).where(User.phone == data.phone)):
        raise HTTPException(409, "phone_taken")
    if data.asha_id is not None:
        asha = db.get(User, data.asha_id)
        if not asha or asha.role != "asha":
            raise HTTPException(422, "asha_id_invalid")
    user = User(role=data.role, name=data.name, phone=data.phone, password_hash=hash_password(data.password),
                language=data.language, village=data.village, condition=data.condition,
                speciality=data.speciality, lat=data.lat, lng=data.lng,
                asha_id=data.asha_id or (_assign_asha(db, data.village) if data.role == "patient" else None))
    db.add(user)
    db.commit()
    return user
