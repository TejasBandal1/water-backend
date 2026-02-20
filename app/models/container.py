from sqlalchemy import Column, Integer, String, Boolean
from app.db.base import Base

class ContainerType(Base):
    __tablename__ = "container_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    is_active = Column(Boolean, default=True)
