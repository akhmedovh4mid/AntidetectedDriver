from pathlib import Path
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from src.models.work_unit import WorkUnit


class ResultWorkUnit(BaseModel):
    status: str
    unit: WorkUnit
    timestamp: datetime
    path: Optional[Path] = None
    context: Optional[str] = None
