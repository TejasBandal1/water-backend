from pydantic import BaseModel

class ClientCreate(BaseModel):
    name: str
    email: str
    phone: str
    address: str
    billing_type: str
    billing_interval: int


class ClientResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    address: str
    billing_type: str
    billing_interval: int

    class Config:
        from_attributes = True
