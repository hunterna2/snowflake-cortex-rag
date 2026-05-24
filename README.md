# Snowflake Cortex RAG Accelerator — Banking Compliance & Policy Q&A

A production-ready, reusable Retrieval-Augmented Generation (RAG) pattern built entirely on Snowflake Cortex. Compliance officers and bankers can ask natural-language questions about internal policies, BSA/AML rules, KYC requirements, and regulatory documents and receive accurate, source-cited answers.

---

## Architecture

```
User Question
      │
      ▼
┌──────────────────────────────────────────────┐
│         Guardrail Layer (Python)             │
│  Blocked-phrase detection · length checks    │
└──────────────────┬───────────────────────────┘
                   │ safe questions only
                   ▼
┌──────────────────────────────────────────────┐
│      Cortex Search  (hybrid retrieval)       │
│  Semantic + keyword search over DOC_CHUNKS   │
│  Optional metadata filter (category, date)   │
└──────────────────┬───────────────────────────┘
                   │ Top-K chunks + citations
                   ▼
┌──────────────────────────────────────────────┐
│  Cortex AI Complete  (mistral-large2 etc.)   │
│  Grounded generation · citation-enforced     │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
          Answer + Source citations
                   │
                   ▼
         QUERY_LOG  (audit & cost table)
```

---

## Quick-start

### 1. Prerequisites

- Snowflake account with Cortex Search and Cortex AI enabled (Business Critical or Enterprise)
- Python 3.11+
- `pip install snowflake-snowpark-python snowflake-cortex pdfplumber python-docx streamlit`

### 2. Snowflake setup (run once)

```sql
-- In Snowsight SQL worksheet, run in order:
source sql/01_setup.sql
-- (load documents first — see step 3)
source sql/02_cortex_search.sql
source sql/03_stored_procs.sql
```

### 3. Ingest documents

```bash
# Set Snowflake credentials
export SF_ACCOUNT=myorg-myaccount
export SF_USER=myuser
export SF_PASSWORD=mypassword

# Ingest a PDF
python python/ingestion.py \
  --file sample_docs/sample_policy.txt \
  --category "BSA/AML" \
  --effective-date 2024-01-01

# Dry-run to preview chunks without uploading
python python/ingestion.py --file myfile.pdf --dry-run
```

Supported formats: `.pdf`, `.docx`, `.doc`, `.txt`

### 4. Run a query (Python)

```python
from python.rag_orchestrator import ask

result = ask("What are the SAR filing thresholds for wire transfers?")
print(result["answer"])
for c in result["citations"]:
    print(f"  Source: {c['source']}, page {c['page']}")
```

### 5. Query via Snowflake stored procedure

```sql
CALL ASK_COMPLIANCE(
  'What are the SAR filing thresholds?',  -- question
  'BSA/AML',                              -- category filter (NULL = all)
  5,                                      -- top-k chunks
  'mistral-large2',                       -- model
  'session-123',                          -- session ID for audit
  'analyst@bank.com'                      -- user email for audit
);
```

---

## Streamlit UI options

### Option A — Streamlit-in-Snowflake (no external hosting needed)

1. In Snowsight: **Projects → Streamlit → + Streamlit App**
2. Paste the contents of `streamlit/app.py`
3. Set the database/schema to `COMPLIANCE_RAG.RAG`

### Option B — Azure-hosted Streamlit (recruiter demo)

**Local demo (no Snowflake required — uses pre-loaded responses):**
```bash
DEMO_MODE=true streamlit run azure_ui/app.py
```

**With live Snowflake connection:**
```bash
export SF_ACCOUNT=... SF_USER=... SF_PASSWORD=...
streamlit run azure_ui/app.py
```

**Deploy to Azure Container Apps:**
```bash
cd azure_ui

# Build and push image
az acr build --registry <your-acr> --image compliance-rag:latest .

# Deploy
az containerapp create \
  --name compliance-rag \
  --resource-group <rg> \
  --image <your-acr>.azurecr.io/compliance-rag:latest \
  --target-port 8501 \
  --ingress external \
  --env-vars \
    SF_ACCOUNT=secretref:sf-account \
    SF_USER=secretref:sf-user \
    SF_PASSWORD=secretref:sf-password
```

**Deploy to Azure App Service (simpler):**
```bash
az webapp up \
  --name compliance-rag-demo \
  --resource-group <rg> \
  --runtime PYTHON:3.11 \
  --sku B1
az webapp config appsettings set \
  --name compliance-rag-demo \
  --resource-group <rg> \
  --settings SF_ACCOUNT=... SF_USER=... SF_PASSWORD=... \
             WEBSITES_PORT=8501
```

---

## File reference

| File | Purpose |
|------|---------|
| `sql/01_setup.sql` | Database, schema, stage, tables, RBAC template |
| `sql/02_cortex_search.sql` | Cortex Search service definition |
| `sql/03_stored_procs.sql` | Snowpark stored procedure + usage view |
| `python/ingestion.py` | Document chunking and upload pipeline |
| `python/guardrails.py` | Responsible AI checks (blocking + advisory) |
| `python/rag_orchestrator.py` | Core RAG logic for local use / Azure UI |
| `streamlit/app.py` | Streamlit-in-Snowflake chat UI |
| `azure_ui/app.py` | Azure-hosted Streamlit demo (with demo mode) |
| `azure_ui/Dockerfile` | Container image for Azure deployment |
| `sample_docs/sample_policy.txt` | Sample BSA/AML policy to test ingestion |

---

## Adding new documents

1. Place the file anywhere accessible.
2. Run `python python/ingestion.py --file <path> --category "<category>"`.
3. The Cortex Search service picks up new rows automatically within `TARGET_LAG` (default: 1 hour). To refresh immediately, re-run `sql/02_cortex_search.sql`.

---

## Governance & responsible AI notes

| Control | Implementation |
|---------|---------------|
| **Hallucination prevention** | System prompt instructs the model to answer only from retrieved sources; if no answer is found it says so. |
| **Blocked topics** | `guardrails.py` blocks questions matching prohibited phrases (money laundering evasion, structuring, etc.) before any LLM call. |
| **Disclaimer** | Every answer includes a standard compliance disclaimer. |
| **Audit log** | Every query is written to `QUERY_LOG` with user, session, model, latency, and guardrail flags. |
| **Cost monitoring** | `RAG_USAGE_SUMMARY` view shows queries and latency by day and model. |
| **Row-level security** | Add Snowflake row access policies on `DOC_CHUNKS` filtered by `DOC_CATEGORY` and map to role to restrict what each user can retrieve. |
| **Model choice** | Swap the `model` parameter to use a smaller/cheaper model for high-volume use cases. |

---

## Reusing this pattern

This is designed as a copy-and-adapt accelerator. To apply it to a different domain:

1. Replace `sample_docs/` with your own documents.
2. Update `GUARDRAIL_BLOCKED_PHRASES` in `guardrails.py` for your domain.
3. Update the `SYSTEM_PROMPT` in `rag_orchestrator.py` / `03_stored_procs.sql`.
4. Rename the Cortex Search service and tables to match your naming convention.
5. Adjust chunk size in `ingestion.py` if your documents have different density.
