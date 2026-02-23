from pydantic import BaseModel
from typing import List
from datetime import datetime
from typing import Optional

class TripContainerCreate(BaseModel):
    container_id: int
    delivered_qty: int
    returned_qty: int

class TripCreate(BaseModel):
    client_id: int
    containers: List[TripContainerCreate]


class AdminMissingBillCreate(BaseModel):
    client_id: int
    driver_id: int
    bill_datetime: datetime
    comments: Optional[str] = None
    containers: List[TripContainerCreate]
