from pydantic import BaseModel

class ContainerCreate(BaseModel):
    name: str
    description: str

class ContainerResponse(BaseModel):
    id: int
    name: str
    description: str

    class Config:
        from_attributes = True
