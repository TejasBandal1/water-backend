from pydantic import BaseModel

class ContainerCreate(BaseModel):
    name: str
    description: str
    is_returnable: bool = True

class ContainerResponse(BaseModel):
    id: int
    name: str
    description: str
    is_returnable: bool

    class Config:
        from_attributes = True
