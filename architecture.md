# Architecture.md
**Reusable Snowflake Cortex RAG Accelerator for Banking Compliance & Policy Q&A**

**Last Updated**: May 24, 2026

## Overview
This project is a **hybrid RAG (Retrieval-Augmented Generation) system** that allows users to ask natural-language questions about bank policies, compliance rules, and regulatory documents. It returns accurate, source-cited answers while maintaining strong cost control and security.

The system supports two modes:
- **Demo Mode** – Zero-cost, pre-loaded answers (currently active)
- **Live Mode** – Real Snowflake Cortex Search + AI (PIN-protected)

## High-Level Architecture
- **Frontend**: Streamlit application written in Python
- **Hosting**: Azure Container Apps (scales to zero when idle)
- **Safety Layer**: Multi-stage guardrails (defense-in-depth)
- **AI/Data Layer**: Snowflake Cortex (Search + AI Functions) for Live Mode
- **Orchestration**: Custom Snowflake stored procedure (`ASK_COMPLIANCE`)

## Request Flow

### Demo Mode (Default)