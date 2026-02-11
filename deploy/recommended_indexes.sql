-- ============================================================================
-- Recommended indexes for SoundCheck Financial analytics views & tables
-- Run these WITHIN each tenant schema (SET search_path TO '<tenant_slug>';)
-- ============================================================================

-- Accounts view performance (on underlying table if materialized)
-- These are recommendations if the underlying tables support it:
CREATE INDEX IF NOT EXISTS idx_accounts_account_id ON accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_accounts_institution ON accounts(institution_name);
CREATE INDEX IF NOT EXISTS idx_accounts_mask ON accounts(mask);

-- Transactions performance
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_account_date ON transactions(account_id, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_pending ON transactions(pending) WHERE pending = true;
CREATE INDEX IF NOT EXISTS idx_transactions_name_trgm ON transactions USING gin (transaction_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_merchant_trgm ON transactions USING gin (merchant_name gin_trgm_ops);

-- App tables (created by Django migrations, but verify these exist)
-- app_client: PK on client_id
-- app_client_account: unique(client_id, account_id), idx on each FK

-- Audit log
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_type ON audit_log(event_type);

-- If using trigram for ILIKE searches, enable the extension:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
