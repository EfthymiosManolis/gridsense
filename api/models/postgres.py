from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BillingAccount(BaseModel):
    premise_id: str
    customer_name: str
    address: Optional[str] = None
    account_status: str
    balance: float = 0.0


class InvoiceCreate(BaseModel):
    premise_id: str
    amount: float
    due_date: datetime
    description: Optional[str] = None
