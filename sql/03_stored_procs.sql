-- =============================================================================
-- 03_stored_procs.sql  |  Snowpark stored procedures for RAG orchestration
-- =============================================================================

USE DATABASE COMPLIANCE_RAG;
USE SCHEMA RAG;
USE WAREHOUSE RAG_WH;

-- ── 1. RAG Query Procedure ────────────────────────────────────────────────────
-- Accepts a question + optional category filter, returns answer + citations.
CREATE OR REPLACE PROCEDURE ASK_COMPLIANCE(
  QUESTION      VARCHAR,
  CATEGORY      VARCHAR DEFAULT NULL,   -- e.g. 'BSA/AML' to scope retrieval
  TOP_K         NUMBER  DEFAULT 5,
  MODEL         VARCHAR DEFAULT 'mistral-large2',
  SESSION_ID    VARCHAR DEFAULT NULL,
  USER_EMAIL    VARCHAR DEFAULT NULL
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES        = ('snowflake-snowpark-python', 'snowflake-cortex')
HANDLER         = 'ask_compliance'
AS $$
import json, time, hashlib
from snowflake.snowpark.context import get_active_session
import snowflake.cortex as cortex

GUARDRAIL_BLOCKED_TOPICS = [
    "how to launder", "avoid detection", "evade reporting",
    "hide transaction", "structuring cash", "bypass kyc",
]

SYSTEM_PROMPT = """You are a banking compliance assistant. Your job is to answer
questions about bank policies, regulatory requirements, and compliance procedures
using ONLY the provided source excerpts. Rules:
- If the answer is not in the sources, say "I could not find this in the provided
  policy documents" — do not fabricate.
- Always cite the source document name and page number at the end of your answer.
- Keep answers professional, clear, and concise.
- Add a disclaimer: "This is an informational summary. Consult your compliance
  officer for official guidance."
"""

def check_guardrails(question: str):
    q = question.lower()
    for phrase in GUARDRAIL_BLOCKED_TOPICS:
        if phrase in q:
            return True, f"Question flagged for policy violation: '{phrase}'"
    return False, None

def build_prompt(question: str, chunks: list) -> str:
    context_block = "\n\n".join(
        f"[Source: {c['SOURCE_FILE']}, Page {c.get('PAGE_NUM','?')}]\n{c['CHUNK_TEXT']}"
        for c in chunks
    )
    return f"""Use the following compliance document excerpts to answer the question.

--- SOURCE EXCERPTS ---
{context_block}
--- END EXCERPTS ---

Question: {question}

Answer:"""

def ask_compliance(session, question, category, top_k, model, session_id, user_email):
    start = time.time()

    # ── Guardrail check ──────────────────────────────────────────────────────
    blocked, guard_msg = check_guardrails(question)
    if blocked:
        log_row = {
            "answer": "I cannot help with that request.",
            "citations": [],
            "guardrail_hit": True,
            "guardrail_msg": guard_msg,
        }
        session.sql("""
            INSERT INTO QUERY_LOG
              (SESSION_ID,USER_EMAIL,QUESTION,ANSWER,CITATIONS,GUARDRAIL_HIT,GUARDRAIL_MSG)
            SELECT %s,%s,%s,%s,PARSE_JSON(%s),%s,%s
        """, params=[session_id, user_email, question,
                     log_row["answer"], "[]", True, guard_msg]).collect()
        return log_row

    # ── Cortex Search retrieval ──────────────────────────────────────────────
    search_filter = ""
    if category:
        search_filter = f', "filter": {{"@eq": {{"DOC_CATEGORY": "{category}"}}}}'

    search_payload = json.dumps({
        "query": question,
        "columns": ["CHUNK_TEXT", "SOURCE_FILE", "DOC_CATEGORY", "PAGE_NUM"],
        "limit": int(top_k),
    })
    # inject optional filter before closing brace
    if category:
        search_payload = search_payload[:-1] + f', "filter": {{"@eq": {{"DOC_CATEGORY": "{category}"}}}}}}'

    raw = session.sql("""
        SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
          'COMPLIANCE_RAG.RAG.COMPLIANCE_SEARCH', %s
        )::VARIANT AS RESULT
    """, params=[search_payload]).collect()

    result_json = json.loads(raw[0]["RESULT"])
    chunks = result_json.get("results", [])

    if not chunks:
        return {
            "answer": "No relevant documents found for your question.",
            "citations": [],
            "guardrail_hit": False,
        }

    # ── Build prompt & call Cortex Complete ─────────────────────────────────
    user_prompt = build_prompt(question, chunks)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]
    answer = cortex.Complete(model, messages)

    # ── Build citation list ──────────────────────────────────────────────────
    seen = set()
    citations = []
    for c in chunks:
        key = (c["SOURCE_FILE"], c.get("PAGE_NUM"))
        if key not in seen:
            seen.add(key)
            citations.append({
                "source": c["SOURCE_FILE"],
                "page":   c.get("PAGE_NUM"),
                "category": c.get("DOC_CATEGORY"),
            })

    # ── Log ──────────────────────────────────────────────────────────────────
    latency_ms = int((time.time() - start) * 1000)
    session.sql("""
        INSERT INTO QUERY_LOG
          (SESSION_ID,USER_EMAIL,QUESTION,ANSWER,CITATIONS,MODEL_USED,LATENCY_MS)
        SELECT %s,%s,%s,%s,PARSE_JSON(%s),%s,%s
    """, params=[
        session_id, user_email, question, answer,
        json.dumps(citations), model, latency_ms,
    ]).collect()

    return {"answer": answer, "citations": citations, "guardrail_hit": False}
$$;


-- ── 2. Cost / Usage Dashboard Query ──────────────────────────────────────────
CREATE OR REPLACE VIEW RAG_USAGE_SUMMARY AS
SELECT
  DATE_TRUNC('day', CREATED_AT)    AS QUERY_DATE,
  MODEL_USED,
  COUNT(*)                          AS TOTAL_QUERIES,
  SUM(GUARDRAIL_HIT::INT)           AS GUARDRAIL_HITS,
  AVG(LATENCY_MS)                   AS AVG_LATENCY_MS,
  MAX(LATENCY_MS)                   AS MAX_LATENCY_MS
FROM QUERY_LOG
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- ── Quick test call (uncomment after docs are loaded) ─────────────────────────
-- CALL ASK_COMPLIANCE(
--   'What are the SAR filing requirements for wire transfers over $10,000?',
--   NULL, 5, 'mistral-large2', 'test-session-1', 'demo@bank.com'
-- );

SELECT 'Stored procedures created' AS STATUS;
