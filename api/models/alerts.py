from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class Alert(BaseModel):
    alert_id: str
    severity: str
    message: str
    node_id: Optional[str] = None
    created_at: datetime
    active: bool = True


class AlertPublish(BaseModel):
    severity: str
    message: str
    node_id: Optional[str] = None
