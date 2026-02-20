from pydantic import BaseModel, EmailStr
from typing import Optional
from typing import Optional

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    client_id: Optional[int] = None
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str
