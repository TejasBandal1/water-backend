from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ClientPriceCreate(BaseModel):
    client_id: int
    container_id: int
    price: float
    effective_from: Optional[datetime] = None
