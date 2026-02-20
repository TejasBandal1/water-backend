from sqlalchemy import Column, Integer, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.db.base import Base


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    container_id = Column(Integer, ForeignKey("container_types.id"))

    quantity = Column(Integer)
    price_snapshot = Column(Float)
    total = Column(Float)

    # 🔥 THIS IS CRITICAL
    container = relationship("ContainerType")
