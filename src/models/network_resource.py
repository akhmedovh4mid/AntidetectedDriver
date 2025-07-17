from pydantic import BaseModel


class NetworkResource(BaseModel):
    url: str
    type: str
