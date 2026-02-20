from pydantic import BaseModel
from typing import List

class TripContainerCreate(BaseModel):
    container_id: int
    delivered_qty: int
    returned_qty: int

class TripCreate(BaseModel):
    client_id: int
    containers: List[TripContainerCreate]
