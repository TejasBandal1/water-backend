from sqlalchemy import Column, Integer, ForeignKey, Float, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)

    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)

    total_amount = Column(Float, default=0)
    amount_paid = Column(Float, default=0)

    status = Column(String, default="draft")

    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)

    client = relationship("Client")

    # 🔥 REQUIRED FOR BACK POPULATION
    trips = relationship("Trip", back_populates="invoice")
