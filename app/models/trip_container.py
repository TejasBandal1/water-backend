from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

class TripContainer(Base):
    __tablename__ = "trip_containers"

    id = Column(Integer, primary_key=True, index=True)

    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    container_id = Column(Integer, ForeignKey("container_types.id"), nullable=False)

    delivered_qty = Column(Integer, nullable=False, default=0)
    returned_qty = Column(Integer, nullable=False, default=0)

    trip = relationship("Trip")
    container = relationship("ContainerType")
