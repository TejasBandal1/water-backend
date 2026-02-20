from sqlalchemy import Column, Integer, String, Boolean
from app.db.base import Base

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    phone = Column(String)
    address = Column(String)

    billing_type = Column(String, nullable=False, default="monthly")
    billing_interval = Column(Integer, nullable=False, default=1)

    is_active = Column(Boolean, default=True)
