import logging

import httpx

from ..config import get_settings

log = logging.getLogger("ruralcare.sms")


def send_sms(phone: str, text: str) -> None:
    """SMS is the primary alert channel for users without mobile data. Safe to use as a background task."""
    s = get_settings()
    if s.sms_provider == "twilio" and s.twilio_account_sid and s.twilio_auth_token and s.twilio_from:
        try:
            r = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
                auth=(s.twilio_account_sid, s.twilio_auth_token),
                data={"To": phone, "From": s.twilio_from, "Body": text},
                timeout=10,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.error("SMS to %s failed: %s", phone, e)
        return
    log.info("SMS (console) to %s: %s", phone, text)
