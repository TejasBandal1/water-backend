from sqlalchemy import Column, Integer, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

class ClientContainerPrice(Base):
    __tablename__ = "client_container_prices"

    id = Column(Integer, primary_key=True, index=True)

    client_id = Column(Integer, ForeignKey("clients.id"))
    container_id = Column(Integer, ForeignKey("container_types.id"))

    price = Column(Float, nullable=False)

    effective_from = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client")
    container = relationship("ContainerType")
