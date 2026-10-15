import datetime as dt

import bcrypt
import jwt

from .config import get_settings

ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, role: str) -> str:
    s = get_settings()
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, s.secret_key, algorithm=ALGO)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
