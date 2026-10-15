from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    user = db.get(User, int(payload["sub"])) if payload else None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token", {"WWW-Authenticate": "Bearer"})
    return user


def require(*roles: str):
    """Role-based access control: `Depends(require("doctor"))`."""
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return user
    return dep
