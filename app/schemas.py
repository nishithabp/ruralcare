import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Lang = Literal["en", "hi", "kn", "ta"]
SYMPTOM_IDS = ("fever", "cough", "blood", "breath", "chest", "dizzy", "thirst", "vomit", "swell")
RED_FLAGS = {"blood", "breath", "chest"}
Symptom = Literal["fever", "cough", "blood", "breath", "chest", "dizzy", "thirst", "vomit", "swell"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth / users ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(pattern=r"^\+?[0-9]{10,15}$")
    password: str = Field(min_length=8, max_length=72)
    language: Lang = "en"
    village: str | None = Field(default=None, max_length=120)
    condition: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class AdminUserIn(RegisterIn):
    role: Literal["patient", "doctor", "asha", "pharmacy", "authority"]
    speciality: str | None = None
    asha_id: int | None = None


class UserOut(ORM):
    id: int
    role: str
    name: str
    phone: str
    language: str
    village: str | None = None
    condition: str | None = None
    speciality: str | None = None
    asha_id: int | None = None


class DoctorOut(UserOut):
    online: bool = False


class UserPatch(BaseModel):
    language: Lang | None = None
    village: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- medicines ----------
class BatchIn(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    medicine_name: str = Field(min_length=1, max_length=120)
    strength: str = Field(min_length=1, max_length=40)
    manufacturer: str = Field(min_length=1, max_length=160)
    batch_no: str = Field(min_length=1, max_length=60)
    expiry: dt.date
    quantity: int = Field(ge=0, le=1_000_000)

    @field_validator("code")
    @classmethod
    def norm_code(cls, v: str) -> str:
        return v.strip().upper()


class BatchOut(ORM):
    id: int
    code: str
    medicine_name: str
    strength: str
    manufacturer: str
    batch_no: str
    expiry: dt.date
    quantity: int
    scan_count: int


class BatchPublic(BaseModel):
    medicine_name: str
    strength: str
    manufacturer: str
    batch_no: str
    expiry: dt.date
    registered_by: str


class VerifyIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class VerifyOut(BaseModel):
    status: Literal["genuine", "expired", "suspicious"]
    reason: Literal["ok", "past_expiry", "duplicate_scans", "not_registered"]
    code: str
    scan_count: int | None = None
    batch: BatchPublic | None = None


class ScanOut(BaseModel):
    id: int
    code: str
    status: str
    reason: str | None
    medicine_name: str | None = None
    strength: str | None = None
    created_at: dt.datetime


class AshaOut(ORM):
    id: int
    name: str
    phone: str


class ReportIn(BaseModel):
    code: str | None = Field(default=None, max_length=64)
    medicine_name: str | None = Field(default=None, max_length=120)
    reason: Literal["expired_sold", "duplicate_scans", "not_registered", "other"]
    note: str | None = Field(default=None, max_length=1000)
    village: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class ReportOut(ORM):
    id: int
    code: str | None
    medicine_name: str | None
    reason: str
    note: str | None
    pharmacy_id: int | None
    village: str | None
    created_at: dt.datetime


# ---------- patient ----------
class PatientMedIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)

    @field_validator("code")
    @classmethod
    def norm_code(cls, v: str) -> str:
        return v.strip().upper()


class PatientMedOut(ORM):
    id: int
    name: str
    strength: str
    expiry: dt.date


class SymptomIn(BaseModel):
    symptoms: list[Symptom] = Field(min_length=1, max_length=len(SYMPTOM_IDS))


class SymptomOut(BaseModel):
    id: int
    urgent: bool
    message_key: Literal["symUrgent", "symOk"]


class SymptomReportOut(ORM):
    id: int
    symptoms: list[str]
    urgent: bool
    visited: bool
    created_at: dt.datetime


# ---------- consultations ----------
class ConsultIn(BaseModel):
    doctor_id: int
    mode: Literal["chat", "audio", "video"] = "chat"


class ConsultOut(ORM):
    id: int
    patient_id: int
    doctor_id: int
    mode: str
    status: str
    created_at: dt.datetime
    ended_at: dt.datetime | None = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: int
    sender_id: int
    body: str
    has_photo: bool
    created_at: dt.datetime


class PrescriptionIn(BaseModel):
    patient_id: int
    consultation_id: int | None = None
    items: list[str] = Field(min_length=1, max_length=20)

    @field_validator("items")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        v = [i.strip() for i in v if i.strip()]
        if not v:
            raise ValueError("items must not be empty")
        return v


class PrescriptionOut(ORM):
    id: int
    consultation_id: int | None
    patient_id: int
    doctor_id: int
    items: list[str]
    created_at: dt.datetime
