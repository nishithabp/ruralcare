"""Daily job (cron): SMS patients whose saved medicines expire soon.

  0 8 * * *  cd /srv && python -m scripts.expiry_job
"""
import datetime as dt

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import PatientMedicine, User
from app.services import messages
from app.services.sms import send_sms


def main() -> None:
    limit = get_settings().expiry_warning_days
    today = dt.date.today()
    sent = 0
    with SessionLocal() as db:
        rows = db.execute(select(PatientMedicine, User).join(User, User.id == PatientMedicine.patient_id)
                          .where(PatientMedicine.expiry >= today,
                                 PatientMedicine.expiry <= today + dt.timedelta(days=limit)))
        for med, patient in rows:
            days = (med.expiry - today).days
            if days in (limit, 14, 7, 3, 1):          # avoid texting every day
                send_sms(patient.phone, messages.render("expiry_patient", patient.language,
                                                        medicine=f"{med.name} {med.strength}", days=days))
                sent += 1
    print(f"expiry SMS sent: {sent}")


if __name__ == "__main__":
    main()
