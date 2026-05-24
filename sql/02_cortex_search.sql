-- =============================================================================
-- 02_cortex_search.sql  |  Create the Cortex Search service
-- Run AFTER 01_setup.sql and AFTER DOC_CHUNKS has been populated
-- =============================================================================

USE DATABASE COMPLIANCE_RAG;
USE SCHEMA RAG;
USE WAREHOUSE RAG_WH;

-- ── Cortex Search service ─────────────────────────────────────────────────────
-- Cortex Search builds a hybrid (semantic + keyword) index over CHUNK_TEXT.
-- Re-run this statement to refresh the index after new chunks are inserted.

CREATE OR REPLACE CORTEX SEARCH SERVICE COMPLIANCE_SEARCH
  ON CHUNK_TEXT
  ATTRIBUTES SOURCE_FILE, DOC_CATEGORY, EFFECTIVE_DT, PAGE_NUM
  WAREHOUSE = RAG_WH
  TARGET_LAG = '1 hour'
AS (
  SELECT
    CHUNK_ID,
    CHUNK_TEXT,
    SOURCE_FILE,
    DOC_CATEGORY,
    EFFECTIVE_DT,
    PAGE_NUM,
    CHUNK_INDEX
  FROM DOC_CHUNKS
);

-- ── Quick smoke test ──────────────────────────────────────────────────────────
-- SELECT PARSE_JSON(
--   SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
--     'COMPLIANCE_RAG.RAG.COMPLIANCE_SEARCH',
--     '{
--       "query": "SAR filing requirements wire transfer",
--       "columns": ["CHUNK_TEXT","SOURCE_FILE","DOC_CATEGORY"],
--       "limit": 5
--     }'
--   )
-- ) AS SEARCH_RESULT;

SELECT 'Cortex Search service created' AS STATUS;
