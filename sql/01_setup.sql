-- =============================================================================
-- 01_setup.sql  |  Snowflake Cortex RAG Accelerator — Initial Setup
-- Run once as ACCOUNTADMIN or a role with CREATE DATABASE / WAREHOUSE privileges
-- =============================================================================

-- ── Warehouse ─────────────────────────────────────────────────────────────────
CREATE WAREHOUSE IF NOT EXISTS RAG_WH
  WAREHOUSE_SIZE = 'SMALL'
  AUTO_SUSPEND   = 60
  AUTO_RESUME    = TRUE
  COMMENT        = 'Cortex RAG accelerator warehouse';

-- ── Database & schema ─────────────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS COMPLIANCE_RAG;
USE DATABASE COMPLIANCE_RAG;

CREATE SCHEMA IF NOT EXISTS RAG;
USE SCHEMA RAG;

-- ── Internal stage for raw documents ──────────────────────────────────────────
CREATE STAGE IF NOT EXISTS DOC_STAGE
  DIRECTORY         = (ENABLE = TRUE)
  COMMENT           = 'Raw compliance docs (PDF, DOCX, TXT)';

-- ── Chunked document store (populated by ingestion pipeline) ──────────────────
CREATE TABLE IF NOT EXISTS DOC_CHUNKS (
  CHUNK_ID      VARCHAR(36)   NOT NULL DEFAULT UUID_STRING() PRIMARY KEY,
  SOURCE_FILE   VARCHAR(512)  NOT NULL,
  PAGE_NUM      NUMBER(6,0),
  CHUNK_INDEX   NUMBER(8,0)   NOT NULL,
  CHUNK_TEXT    VARCHAR(8192) NOT NULL,
  DOC_CATEGORY  VARCHAR(128),           -- e.g. 'BSA/AML', 'KYC', 'OFAC'
  EFFECTIVE_DT  DATE,
  CREATED_AT    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ── Query log for audit & cost monitoring ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS QUERY_LOG (
  LOG_ID        VARCHAR(36)    NOT NULL DEFAULT UUID_STRING() PRIMARY KEY,
  SESSION_ID    VARCHAR(64),
  USER_EMAIL    VARCHAR(256),
  QUESTION      VARCHAR(4096)  NOT NULL,
  ANSWER        VARCHAR(16384),
  CITATIONS     VARIANT,
  MODEL_USED    VARCHAR(128),
  TOKENS_IN     NUMBER(10,0),
  TOKENS_OUT    NUMBER(10,0),
  LATENCY_MS    NUMBER(10,0),
  GUARDRAIL_HIT BOOLEAN        DEFAULT FALSE,
  GUARDRAIL_MSG VARCHAR(512),
  CREATED_AT    TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()
);

-- ── Role & grants (adapt to your RBAC) ────────────────────────────────────────
-- CREATE ROLE IF NOT EXISTS RAG_USER;
-- GRANT USAGE ON WAREHOUSE RAG_WH          TO ROLE RAG_USER;
-- GRANT USAGE ON DATABASE  COMPLIANCE_RAG  TO ROLE RAG_USER;
-- GRANT USAGE ON SCHEMA    COMPLIANCE_RAG.RAG TO ROLE RAG_USER;
-- GRANT SELECT ON TABLE    DOC_CHUNKS       TO ROLE RAG_USER;
-- GRANT INSERT ON TABLE    QUERY_LOG        TO ROLE RAG_USER;

SELECT 'Setup complete' AS STATUS;
