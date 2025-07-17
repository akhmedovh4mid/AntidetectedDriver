from pydantic import BaseModel


class LocationData(BaseModel):
    timezone: str
    locale: str
    longitude: float
    lantitude: float
    zipcode: str
