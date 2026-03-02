from typing import Optional

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    client_id: Optional[int] = None


class UserUpdate(BaseModel):
    name: str
    email: str
    role: str
    password: Optional[str] = None
    client_id: Optional[int] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    client_id: Optional[int] = None

    class Config:
        from_attributes = True
