from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True)
    hashed_password = Column(String)

    role_id = Column(Integer, ForeignKey("roles.id"))
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)

    role = relationship("Role")
    client = relationship("Client")
