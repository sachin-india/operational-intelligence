-- Operational Intelligence — Postgres initialisation
-- Runs once when the container is first created.
-- Application tables (audit_log, etc.) are created by SQLAlchemy in Phase 1.2.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
