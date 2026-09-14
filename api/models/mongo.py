from pydantic import BaseModel
from typing import Optional


class Equipment(BaseModel):
    asset_id: str
    equipment_type: str
    name: str
    status: str
    location: Optional[str] = None
    specifications: dict = {}
