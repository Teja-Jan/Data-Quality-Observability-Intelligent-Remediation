# Enterprise Data Quality Observability & Intelligent Remediation

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Teja-Jan/Data-Quality-Observability-Intelligent-Remediation/blob/Data-Quality-Observability-and-Intelligent-Remediation/Launch_in_Colab.ipynb)

## Overview
An AI-Agent orchestrated platform for modern data quality. By combining deterministic **23-dimension profiling** with an **Autonomous Reasoning Layer (Meta Llama 3)**, the system identifies "silent data decay" and programmatically repairs anomalies.

## Features
- **Plug & Play Connectivity**: Snowflake, RDBMS, API, and Flat Files.
- **Autonomous Remediation**: AI-driven "Auto-Fix" for minor formatting and standardizations.
- **Multi-Model Intelligence**: Powered by **LiteLLM** and **Llama 3** via Ollama.
- **PII Governance**: Real-time security profiling and RBAC management.
- **Comparative Analysis**: Live Pre-Fix vs. Post-Fix health deltas.

## Quick Start (Colab)
Click the **Open in Colab** badge above to launch the interactive demo environment immediately.

## Manual Installation
1. Clone the repo:
   ```bash
   git clone https://github.com/Teja-Jan/Data-Quality-Observability-Intelligent-Remediation.git
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   streamlit run src/app.py
   ```

## Architecture
The system follows a **ReAct (Reason + Act)** pattern, using a custom agentic loop to navigate the lifecycle of data health from detection to persistent remediation.

---
© 2026 Enterprise Data Quality Team
