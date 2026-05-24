"""
ingestion.py — Document ingestion pipeline for Snowflake Cortex RAG.

Supports PDF, DOCX, and plain text. Chunks documents with overlap,
attaches metadata, and upserts into DOC_CHUNKS via Snowpark.

Usage (local, with Snowpark connection):
    python ingestion.py --file policies/bsa_aml_policy.pdf \
                        --category "BSA/AML" \
                        --effective-date 2024-01-01
"""

import argparse
import hashlib
import os
import uuid
from datetime import date
from pathlib import Path

CHUNK_SIZE = 1000      # characters
CHUNK_OVERLAP = 150    # characters of overlap between consecutive chunks


# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_from_txt(path: str) -> list[tuple[int, str]]:
    """Returns list of (page_num, text). TXT has a single page."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        return [(1, f.read())]


def extract_text_from_pdf(path: str) -> list[tuple[int, str]]:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pip install pdfplumber to process PDFs")
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append((i, text))
    return pages


def extract_text_from_docx(path: str) -> list[tuple[int, str]]:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("pip install python-docx to process DOCX files")
    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    return [(1, full_text)]


def extract_pages(path: str) -> list[tuple[int, str]]:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(path)
    else:
        return extract_text_from_txt(path)


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return [c for c in chunks if len(c) > 50]  # drop tiny trailing fragments


def build_chunks(path: str, category: str, effective_dt: date) -> list[dict]:
    source_file = Path(path).name
    pages = extract_pages(path)
    rows = []
    global_idx = 0
    for page_num, page_text in pages:
        for chunk in chunk_text(page_text):
            rows.append({
                "CHUNK_ID":     str(uuid.uuid4()),
                "SOURCE_FILE":  source_file,
                "PAGE_NUM":     page_num,
                "CHUNK_INDEX":  global_idx,
                "CHUNK_TEXT":   chunk,
                "DOC_CATEGORY": category,
                "EFFECTIVE_DT": str(effective_dt),
            })
            global_idx += 1
    return rows


# ── Snowpark upload ────────────────────────────────────────────────────────────

def upload_to_snowflake(rows: list[dict], connection_params: dict) -> None:
    from snowflake.snowpark import Session
    import pandas as pd

    session = Session.builder.configs(connection_params).create()
    df = pd.DataFrame(rows)
    snowpark_df = session.create_dataframe(df)

    # Delete existing chunks for this source file before re-inserting
    source = rows[0]["SOURCE_FILE"]
    session.sql(
        f"DELETE FROM COMPLIANCE_RAG.RAG.DOC_CHUNKS WHERE SOURCE_FILE = '{source}'"
    ).collect()

    snowpark_df.write.mode("append").save_as_table("COMPLIANCE_RAG.RAG.DOC_CHUNKS")
    print(f"  Uploaded {len(rows)} chunks for '{source}'")
    session.close()


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest compliance documents into Snowflake RAG")
    parser.add_argument("--file",           required=True,  help="Path to document (PDF/DOCX/TXT)")
    parser.add_argument("--category",       default="General", help="Compliance category (e.g. BSA/AML)")
    parser.add_argument("--effective-date", default=str(date.today()))
    parser.add_argument("--account",        default=os.getenv("SF_ACCOUNT"))
    parser.add_argument("--user",           default=os.getenv("SF_USER"))
    parser.add_argument("--password",       default=os.getenv("SF_PASSWORD"))
    parser.add_argument("--warehouse",      default="RAG_WH")
    parser.add_argument("--dry-run",        action="store_true", help="Print chunks without uploading")
    args = parser.parse_args()

    print(f"Processing: {args.file}")
    chunks = build_chunks(args.file, args.category, args.effective_date)
    print(f"  Generated {len(chunks)} chunks")

    if args.dry_run:
        for i, c in enumerate(chunks[:3]):
            print(f"\n  --- Chunk {i} (page {c['PAGE_NUM']}) ---")
            print(f"  {c['CHUNK_TEXT'][:200]}...")
        return

    conn = {
        "account":   args.account,
        "user":      args.user,
        "password":  args.password,
        "warehouse": args.warehouse,
        "database":  "COMPLIANCE_RAG",
        "schema":    "RAG",
    }
    upload_to_snowflake(chunks, conn)
    print("Done. Refresh the Cortex Search service if TARGET_LAG is not set to auto.")


if __name__ == "__main__":
    main()
