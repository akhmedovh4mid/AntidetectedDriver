from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from src.models.proxy_unit import ProxyUnit
from src.models.work_unit import WorkUnit


class WaitWorkUnit(BaseModel):
    work: WorkUnit
    proxy: Optional[ProxyUnit]
    timestamp: datetime
    attempts: int
