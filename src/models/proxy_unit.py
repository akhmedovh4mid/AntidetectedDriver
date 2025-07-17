from pydantic import BaseModel


class ProxyUnit(BaseModel):
    host: str
    port: int
    username: str
    password: str
    timezone: str
    locale: str
    longitude: float
    lantitude: float
    zipcode: str
