from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class BillingAccount(BaseModel):
    premise_id: str
    customer_name: str
    address: Optional[str] = None
    account_status: str
    balance: Decimal = Decimal('0.00')
    requires_reconciliation: bool = False


class InvoiceCreate(BaseModel):
    premise_id: str = Field(min_length=1, max_length=50)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    billing_period: date
    due_date: AwareDatetime
    description: Optional[str] = None

    @field_validator('billing_period')
    @classmethod
    def require_month_start(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError('billing_period must be the first day of the billed month')
        return value


class InvoiceRecord(BaseModel):
    invoice_id: int
    premise_id: str
    amount: Decimal
    billing_period: date
    due_date: AwareDatetime
    description: Optional[str] = None


class InvoiceResponse(BaseModel):
    message: str
    created: bool
    invoice: InvoiceRecord
