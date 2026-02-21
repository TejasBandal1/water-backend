from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _unauthorized(detail: str = "Invalid authentication") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _unauthorized("Missing authentication token")

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except JWTError:
        raise _unauthorized("Invalid authentication token")

    email = payload.get("sub") or payload.get("email")
    if not isinstance(email, str) or not email.strip():
        raise _unauthorized("Invalid token payload")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise _unauthorized("User not found")

    return user


def require_role(required_roles: list[str]):
    allowed_roles = {role.strip().upper() for role in required_roles if role and role.strip()}

    def role_checker(user: User = Depends(get_current_user)) -> User:
        user_role = (user.role.name if user.role else "").upper()

        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User role not assigned",
            )

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        return user

    return role_checker
