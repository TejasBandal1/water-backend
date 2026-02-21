from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserCreate


router = APIRouter(prefix="/auth", tags=["Auth"])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    role_name = (user.role or "").strip().lower()
    role = db.query(Role).filter(func.lower(Role.name) == role_name).first()
    if not role:
        raise HTTPException(status_code=400, detail="Invalid role")

    email = (user.email or "").strip().lower()
    existing_user = db.query(User).filter(func.lower(User.email) == email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    new_user = User(
        name=(user.name or "").strip(),
        email=email,
        hashed_password=hash_password(user.password),
        role_id=role.id,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User created successfully"}


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = (form_data.username or "").strip().lower()
    db_user = db.query(User).filter(func.lower(User.email) == email).first()

    if not db_user or not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not db_user.role or not db_user.role.name:
        raise HTTPException(status_code=403, detail="User role not assigned")

    access_token = create_access_token(
        data={
            "sub": db_user.email,
            "role": db_user.role.name.lower(),
            "name": db_user.name or "",
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
