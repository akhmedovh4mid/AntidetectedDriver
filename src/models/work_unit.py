from typing import Optional
from pydantic import BaseModel


class WorkUnit(BaseModel):
    link: str
    title: str
    lang: str
    image_url: str
    description: Optional[str]
    is_downloaded: bool
