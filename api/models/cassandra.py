from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    sensor_id: str
    region_id: str = Field(min_length=1)
    reading_time: datetime
    metric_type: Literal[
        "voltage",
        "current",
        "power_factor",
        "temp",
    ]
    value: float
    unit: str
    quality_flag: int = Field(default=0, ge=0, le=2)
