from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)

    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 🔥 ADD THIS INSIDE CLASS
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client")
    driver = relationship("User")
    invoice = relationship("Invoice", back_populates="trips")
