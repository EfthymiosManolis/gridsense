-- Preserve historical invoices: their unknown billing period remains NULL.
-- NOT VALID constraints protect new writes without rewriting historical data.
ALTER TABLE invoices ADD COLUMN IF NOT EXISTS billing_period DATE;

CREATE UNIQUE INDEX IF NOT EXISTS invoices_premise_period_unique
    ON invoices (premise_id, billing_period);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'invoices'::regclass AND conname = 'invoices_valid_amount'
    ) THEN
        ALTER TABLE invoices ADD CONSTRAINT invoices_valid_amount
            CHECK (amount > 0 AND amount <= 9999999999.99) NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'invoices'::regclass AND conname = 'invoices_valid_period'
    ) THEN
        ALTER TABLE invoices ADD CONSTRAINT invoices_valid_period
            CHECK (billing_period IS NOT NULL AND EXTRACT(DAY FROM billing_period) = 1)
            NOT VALID;
    END IF;
END $$;
