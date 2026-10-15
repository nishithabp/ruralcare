"""Create the first drug-authority account, and optionally demo data.

  python -m scripts.seed --authority-phone 9000000001 --authority-password 'S3cure-pass!'
  python -m scripts.seed --demo
"""
import argparse
import datetime as dt

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Batch, User
from app.security import hash_password


def user(db, role, name, phone, password, **kw):
    u = db.scalar(select(User).where(User.phone == phone))
    if not u:
        u = User(role=role, name=name, phone=phone, password_hash=hash_password(password), **kw)
        db.add(u)
        db.commit()
    return u


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authority-phone", default="9000000001")
    ap.add_argument("--authority-password", default="ChangeMe123!")
    ap.add_argument("--demo", action="store_true", help="also create demo doctors, ASHA, pharmacy, patient and batches")
    a = ap.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user(db, "authority", "District Drug Control Office", a.authority_phone, a.authority_password)
        if a.demo:
            pw = "Demo12345!"
            asha = user(db, "asha", "Meena", "9000000010", pw, village="Melur", language="kn")
            user(db, "doctor", "Dr. Anitha Rao", "9000000020", pw, speciality="General physician")
            user(db, "doctor", "Dr. Karthik S", "9000000021", pw, speciality="Diabetes specialist")
            user(db, "doctor", "Dr. Farah Khan", "9000000022", pw, speciality="Chest and TB specialist")
            ph = user(db, "pharmacy", "Sri Murugan Medicals", "9000000030", pw, village="Melur", lat=12.92, lng=79.13)
            user(db, "patient", "Lakshmi", "9000000040", pw, village="Melur", condition="Diabetes and high BP",
                 language="ta", asha_id=asha.id)
            samples = [("MTF-2231-B07", "Metformin", "500 mg", "SunRise Labs, Hyderabad", "B07", dt.date(2027, 8, 31), 40),
                       ("AML-1904-C12", "Amlodipine", "5 mg", "GreenLeaf Pharma, Chennai", "C12", dt.date(2026, 5, 31), 25),
                       ("RIF-7788-X91", "Rifampicin", "450 mg", "Medicorp Remedies, Pune", "X91", dt.date(2027, 11, 30), 60)]
            for code, name, strength, maker, batch_no, exp, qty in samples:
                if not db.scalar(select(Batch).where(Batch.code == code)):
                    db.add(Batch(code=code, medicine_name=name, strength=strength, manufacturer=maker,
                                 batch_no=batch_no, expiry=exp, quantity=qty, pharmacy_id=ph.id))
            db.commit()
            print("Demo users (password Demo12345!): patient 9000000040, doctor 9000000020, "
                  "ASHA 9000000010, pharmacy 9000000030")
        print(f"Authority login: {a.authority_phone}")


if __name__ == "__main__":
    main()
