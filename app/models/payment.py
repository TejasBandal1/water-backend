from sqlalchemy import Column, Integer, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)

    amount = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)  # 🔥 ADD THIS

    invoice = relationship("Invoice")
    created_at = Column(DateTime, default=datetime.utcnow)
