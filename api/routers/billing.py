from fastapi import APIRouter, HTTPException
from api.models.postgres import BillingAccount, InvoiceCreate
from api.db.postgres import get_postgres_pool



router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/account/{premise_id}", response_model=BillingAccount)
async def get_billing_account(premise_id: str):
    pool = get_postgres_pool()

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT premise_id,
                   customer_name,
                   address,
                   account_status,
                   balance
            FROM consumer_accounts
            WHERE premise_id = $1
            """,
            premise_id
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Billing account not found"
        )

    return BillingAccount(**dict(row))


@router.post("/invoice")
async def create_invoice(invoice: InvoiceCreate):
    pool = get_postgres_pool()

    async with pool.acquire() as connection:
        async with connection.transaction():
            account = await connection.fetchrow(
                """
                SELECT premise_id
                FROM consumer_accounts
                WHERE premise_id = $1
                FOR UPDATE
                """,
                invoice.premise_id
            )

            if account is None:
                raise HTTPException(
                    status_code=404,
                    detail="Billing account not found"
                )

            row = await connection.fetchrow(
                """
                INSERT INTO invoices
                    (premise_id, amount, due_date, description)
                VALUES
                    ($1, $2, $3, $4)
                RETURNING invoice_id,
                          premise_id,
                          amount,
                          due_date,
                          description
                """,
                invoice.premise_id,
                invoice.amount,
                invoice.due_date,
                invoice.description
            )

    return {
        "message": "Invoice created successfully",
        "invoice": dict(row)
}
