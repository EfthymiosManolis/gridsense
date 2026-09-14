CREATE TABLE IF NOT EXISTS consumer_accounts (
    premise_id VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    address TEXT,
    account_status VARCHAR(30) NOT NULL DEFAULT 'active',
    balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id BIGSERIAL PRIMARY KEY,
    premise_id VARCHAR(50) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    due_date TIMESTAMPTZ NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_invoice_account
        FOREIGN KEY (premise_id)
        REFERENCES consumer_accounts(premise_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_invoices_premise_id
    ON invoices(premise_id);

CREATE INDEX IF NOT EXISTS idx_invoices_due_date
    ON invoices(due_date);
