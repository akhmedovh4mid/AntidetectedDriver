from pydantic import BaseModel


class ProxyAuth(BaseModel):
    username: str
    password: str
