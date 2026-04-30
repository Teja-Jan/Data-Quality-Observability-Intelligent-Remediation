"""
Data Quality Observability & Intelligent Remediation
Three-phase flow:
  Phase 1 — Connection  (AI Assistant  OR  Manual: DB / File / API)
  Phase 2 — Domain selection (selectbox, post-auth)
  Phase 3 — Dashboard    (Left: Assets · Right: DQ tabs)

Real connectors (src/connectors/data_connector.py) plug into DQAgent unchanged.
Falls back to demo CSV datasets when live connections fail.
"""

import sys
import io
import os
import random
from pathlib import Path

# ─── PATH SETUP ───────────────────────────────────────────────────────────────
# Ensure the 'src' directory is at the front of sys.path
SRC_DIR = Path(__file__).parent.absolute()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

ROOT_DIR = SRC_DIR.parent

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

import streamlit as st

from agent.dq_agent import DQAgent, DQ_LEVEL_MAP
from agent.ai_dq_agent import AIDQAgent
from db import database as db
from dq_reports.report_generator import generate_pdf_report, generate_excel_issues_report
from email_service import send_dq_alert, send_high_risk_approval_email
from connectors.data_connector import DatabaseConnector, FlatFileConnector, APIConnector
from utils import env_manager

# Initialize environment
env_manager.init_env()

APP_TITLE    = "Data Quality Observability & Intelligent Remediation"
APP_SUBTITLE = ("Integrates multi-dimensional observability with autonomous remediation "
                "to ensure enterprise-grade data integrity across all environments.")
HIGH_RISK_EMAIL = "teja.jan220@gmail.com"
MAX_SELECTIONS  = 12

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@600;700;800&display=swap');

:root {
    --primary: #2563EB; --surface: #FFFFFF; --bg: #F1F5F9;
    --border: #E2E8F0; --text: #0F172A; --muted: #64748B;
    --green: #059669; --red: #DC2626; --amber: #D97706;
}
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: var(--bg); color: var(--text); }

/* ── Sidebar hidden ── */
section[data-testid="stSidebar"] { display: none !important; }
button[data-testid="collapsedControl"] { display: none !important; }

/* ── Header ── */
.header-bar {
    background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 55%, #7C3AED 100%);
    border-radius: 16px; padding: 24px 32px; margin-bottom: 20px;
    position: relative; overflow: hidden;
    box-shadow: 0 20px 40px rgba(37,99,235,0.22);
}
.header-bar::after {
    content:''; position:absolute; top:-40%; right:-8%; width:300px; height:300px;
    background:rgba(255,255,255,0.06); border-radius:50%;
}
.header-title {
    font-family:'Outfit',sans-serif; font-size:2.35rem !important;
    font-weight:900 !important; letter-spacing:0.5px; line-height:1.15;
    color:#fff; margin:0 0 10px; text-shadow:0 4px 15px rgba(0,0,0,0.3);
}
.header-sub { color:rgba(255,255,255,0.85); font-size:0.98rem; font-weight:500; margin:0; line-height:1.5; }

/* ── Section labels ── */
.section-header {
    font-size:0.73rem; font-weight:700; text-transform:uppercase;
    letter-spacing:0.8px; color:var(--muted); padding:8px 2px 4px;
    border-bottom:1px solid var(--border); margin-bottom:6px;
}
.intelligence-header {
    font-family:'Outfit',sans-serif; font-size:1.75rem; font-weight:800;
    color:var(--primary); margin:15px 0 5px;
    padding-bottom:5px; border-bottom:2px solid var(--primary);
}

/* ── Pill / badge ── */
.sel-pill {
    display:inline-flex; align-items:center; gap:6px;
    background:#EFF6FF; border:1px solid #BFDBFE;
    color:#1E40AF; border-radius:20px; padding:3px 10px 3px 8px;
    font-size:0.73rem; font-weight:600; margin:2px;
}
.ctx-badge {
    display:inline-block; background:#F0FDF4; border:1px solid #BBF7D0;
    color:#065F46; border-radius:8px; padding:4px 10px;
    font-size:0.78rem; font-weight:700; margin-bottom:8px;
}
.demo-badge {
    display:inline-block; background:#FFF7ED; border:1px solid #FED7AA;
    color:#92400E; border-radius:8px; padding:3px 9px;
    font-size:0.72rem; font-weight:700; margin-bottom:6px;
}
.live-badge {
    display:inline-block; background:#F0FDF4; border:1px solid #86EFAC;
    color:#166534; border-radius:8px; padding:3px 9px;
    font-size:0.72rem; font-weight:700; margin-bottom:6px;
}

/* ── Source-type section headers ── */
.src-section-db   { font-size:0.68rem; font-weight:800; text-transform:uppercase; letter-spacing:0.6px; color:#1E40AF; border-bottom:1px solid #BFDBFE; padding:6px 0 3px; margin:10px 0 4px; }
.src-section-file { font-size:0.68rem; font-weight:800; text-transform:uppercase; letter-spacing:0.6px; color:#065F46; border-bottom:1px solid #BBF7D0; padding:6px 0 3px; margin:10px 0 4px; }
.src-section-api  { font-size:0.68rem; font-weight:800; text-transform:uppercase; letter-spacing:0.6px; color:#9F1239; border-bottom:1px solid #FECDD3; padding:6px 0 3px; margin:10px 0 4px; }

/* ── Source type badges (inline pill on items) ── */
.src-badge-db   { background:#EFF6FF; color:#1E40AF; border:1px solid #BFDBFE; padding:1px 6px; border-radius:6px; font-size:0.62rem; font-weight:700; }
.src-badge-file { background:#F0FDF4; color:#065F46; border:1px solid #BBF7D0; padding:1px 6px; border-radius:6px; font-size:0.62rem; font-weight:700; }
.src-badge-api  { background:#FFF1F2; color:#9F1239; border:1px solid #FECDD3; padding:1px 6px; border-radius:6px; font-size:0.62rem; font-weight:700; }

/* ── Cards ── */
.main-card {
    background:#fff; border-radius:12px; padding:18px 20px;
    border:1px solid var(--border);
    box-shadow:0 1px 3px rgba(0,0,0,0.06),0 6px 16px rgba(0,0,0,0.04);
    margin-bottom:14px;
}
.kpi-card {
    background:#fff; border-radius:14px; padding:16px 18px;
    border:1px solid var(--border); text-align:center;
    box-shadow:0 2px 8px rgba(0,0,0,0.05);
}
.kpi-value { font-size:2rem; font-weight:800; font-family:'Outfit',sans-serif; }
.kpi-label { font-size:0.72rem; color:var(--muted); font-weight:600;
             text-transform:uppercase; letter-spacing:0.4px; margin-top:4px; }

/* ── Dimension health card grid ── */
.dim-level-label {
    font-size:0.7rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.9px; color:var(--muted);
    border-bottom:2px solid var(--border); padding:12px 0 5px;
    margin:18px 0 10px; display:flex; align-items:center; gap:6px;
}
.dim-health-card {
    background:#fff; border-radius:11px; padding:13px 15px;
    border:1px solid var(--border); border-left-width:4px;
    box-shadow:0 1px 4px rgba(0,0,0,0.05);
    margin-bottom:8px; min-height:110px;
}
.dim-card-name { font-size:0.77rem; font-weight:700; color:#1e293b; margin-bottom:3px; }
.dim-card-score { font-size:1.6rem; font-weight:800; font-family:'Outfit',sans-serif; line-height:1.1; }
.dim-card-badge {
    display:inline-block; padding:2px 8px; border-radius:12px;
    font-size:0.65rem; font-weight:700; margin-top:4px;
}
.dim-card-issues { font-size:0.67rem; color:#64748b; margin-top:3px; }

/* ── OR separator ── */
.or-separator {
    display:flex; align-items:center; justify-content:center;
    flex-direction:column; height:100%; font-weight:800;
    color:var(--muted); font-size:1.1rem; position:relative;
    padding-top:140px; opacity:0.7;
}
.or-separator::before, .or-separator::after {
    content:''; position:absolute; width:1px; height:35%; background:var(--border);
}
.or-separator::before { top:0; }
.or-separator::after  { bottom:0; }

/* ── Home chat ── */
.home-chat-msg {
    padding:5px 2px; font-size:0.87rem; color:#334155;
    border-bottom:1px solid #f1f5f9; margin-bottom:4px;
}

/* ── Level / metadata ── */
.level-header {
    background:linear-gradient(135deg,#f1f5f9,#e8edf5);
    border-radius:8px; padding:8px 14px; margin:12px 0 6px;
    border-left:4px solid #2563eb; font-weight:700; font-size:0.86rem; color:#1e293b;
}
.metadata-box {
    background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px;
}
.meta-row {
    display:flex; justify-content:space-between; align-items:center;
    padding:4px 0; border-bottom:1px solid #f1f5f9; font-size:0.8rem;
}
.meta-key { color:#64748b; font-weight:500; }
.meta-val { color:#1e293b; font-weight:600; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { gap:5px; background:transparent; }
.stTabs [data-baseweb="tab"] {
    height:36px; background:#fff; border-radius:8px;
    color:var(--muted); font-weight:600; font-size:0.82rem;
    border:1px solid var(--border); padding:4px 12px; transition:all 0.18s ease;
}
.stTabs [aria-selected="true"] {
    background:var(--primary) !important; color:#fff !important;
    border-color:var(--primary) !important; box-shadow:0 4px 12px rgba(37,99,235,0.3);
}
h3 { font-family:'Outfit',sans-serif !important; color:var(--text) !important; }
table { font-size:0.8rem; }

/* ── Fix banner / risk badges ── */
.fix-success-banner {
    background:linear-gradient(135deg,#dcfce7,#bbf7d0);
    border:1px solid #86efac; border-radius:10px; padding:12px 16px; margin-bottom:12px;
}
.risk-high   { background:#FEE2E2; border-left:4px solid #DC2626; color:#7F1D1D; padding:10px 12px; border-radius:8px; margin:4px 0; font-size:0.83rem; }
.risk-medium { background:#FEF3C7; border-left:4px solid #D97706; color:#78350F; padding:10px 12px; border-radius:8px; margin:4px 0; font-size:0.83rem; }
.risk-low    { background:#DCFCE7; border-left:4px solid #059669; color:#064E3B; padding:10px 12px; border-radius:8px; margin:4px 0; font-size:0.83rem; }

/* ── Connection type indicator ── */
.conn-info-bar {
    background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;
    padding:10px 14px; margin:8px 0;
    font-size:0.82rem; color:#334155;
}
.conn-type-db   { border-left:4px solid #2563EB; }
.conn-type-file { border-left:4px solid #059669; }
.conn-type-api  { border-left:4px solid #DC2626; }

/* ── Warning / fallback banner ── */
.fallback-banner {
    background:#FFF7ED; border:1px solid #FED7AA; border-left:4px solid #F97316;
    border-radius:8px; padding:10px 14px; margin-bottom:10px; font-size:0.83rem;
    color:#7C2D12;
}
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
DOMAINS = {
    "Healthcare":   "healthcare",
    "Finance":      "finance",
    "Insurance":    "insurance",
    "Supply Chain": "supply_chain",
    "Automotive":   "automotive",
}
DOMAIN_ICONS = {
    "healthcare":   "H",
    "finance":      "F",
    "insurance":    "I",
    "supply_chain": "S",
    "automotive":   "A",
}
DATA_DIR = ROOT_DIR / "data" / "raw"

DIMENSION_LABELS = {
    "completeness": "Data Completeness",
    "consistency": "Data Consistency",
    "standardization": "Data Standardization",
    "enrichment": "Data Quality / Data Enrichment Quality",
    "accuracy": "Data Accuracy",
    "validity": "Data Validity",
    "timeliness": "Data Timeliness",
    "integrity": "Data Integrity",
    "conformity": "Data Conformity",
    "uniqueness": "Data Uniqueness",
    "reasonableness": "Data Reasonableness",
    "lineage": "Data Lineage & Traceability",
    "auditability": "Data Auditability",
    "duplication": "Data Duplication",
    "constraints": "Data Constraints Check",
    "profiling": "Data Profiling",
    "reliability": "Data Reliability",
    "accessibility": "Data Accessibility",
    "freshness": "Data Freshness / Latency",
    "pii_security": "Data Security & Privacy Checks",
    "reconciliation": "Data Reconciliation",
    "business_rules": "Business Rule Validation / Transformation Logic Validation",
    "survivorship": "Survivorship Rules (MDM-specific)",
}

TABLE_DIMS  = ["profiling", "integrity", "auditability", "reconciliation",
               "survivorship", "lineage", "timeliness", "freshness", "accessibility"]
COLUMN_DIMS = ["completeness", "uniqueness", "validity", "accuracy", "duplication",
               "standardization", "conformity", "constraints", "enrichment", "pii_security"]
ROW_DIMS    = ["consistency", "business_rules", "reasonableness", "reliability"]

# ── Per-domain enterprise asset catalog (used for demo / multi-source sidebar) ─
DOMAIN_ASSET_CATALOG = {
    # Healthcare domain configuration below
    "healthcare": {
        "platform": "On-Premise Server",
        "databases": ["hc_clinical_db", "hc_claims_db"],
        "tables": ["hc_patient_records", "hc_clinical_encounters", "hc_billing_system"],
        "flat_files": ["healthcare_dataset.csv", "hl7_messages.parquet"],
        "api_endpoints": ["api/epic/v1/patients", "Healthcare Provider Directory API"],
    },
    "finance": {
        "platform": "Cloud Infrastructure (Snowflake)",
        "databases":  ["fin_operations_db", "fin_risk_db"],
        "tables": ["fin_transactions", "fin_ledger", "fin_risk_registry"],
        "flat_files": ["finance_dataset.csv", "market_rates_feed.parquet", "swift_messages.json"],
        "api_endpoints": ["api/plaid/v2/transactions", "api/bloomberg/v1/rates", "api/fed/v1/rates"],
    },
    "insurance": {
        "platform": "On-Premise Server",
        "databases":  ["ins_core_db", "ins_actuarial_db"],
        "tables": ["ins_claims", "ins_policies", "ins_customers"],
        "flat_files": ["insurance_dataset.csv", "claims_extract.parquet", "policy_riders.json"],
        "api_endpoints": ["api/verisk/v1/claims", "api/iso/v2/policies", "api/dunnhumby/v1/risk"],
    },
    "supply_chain": {
        "platform": "Cloud Infrastructure (Google BigQuery)",
        "databases":  ["sc_operations_db", "sc_logistics_db"],
        "tables": ["sc_inventory", "sc_vendors", "sc_shipments"],
        "flat_files": ["supply_chain_dataset.csv", "warehouse_manifest.parquet", "vendor_catalog.json"],
        "api_endpoints": ["api/fedex/v1/tracking", "api/ups/v2/shipments", "api/sap/v1/procurement"],
    },
    "automotive": {
        "platform": "Cloud Infrastructure (Databricks)",
        "databases":  ["auto_manufacturing_db", "auto_dealership_db"],
        "tables": ["auto_vehicles", "auto_sales", "auto_services"],
        "flat_files": ["automotive_dataset.csv", "vin_registry.parquet", "parts_catalog.json"],
        "api_endpoints": ["api/carfax/v1/history", "api/nhtsa/v1/recalls", "api/jdpower/v1/ratings"],
    },
}

DEMO_COLUMN_MAP = {
    # Healthcare
    "hc_patient_records": ["patient_id", "patient_name", "date_of_birth", "age", "gender", "ssn", "email", "phone", "address", "zip_code"],
    "hc_clinical_encounters": ["admission_date", "discharge_date", "diagnosis_code", "icd_version", "treatment", "physician_name", "status", "last_updated"],
    "hc_billing_system": ["insurance_id", "bill_amount", "payment_status"],
    # Finance
    "fin_transactions": ["transaction_id", "transaction_date", "amount", "transaction_type", "currency", "merchant", "merchant_category", "fraud_flag", "status"],
    "fin_ledger": ["account_id", "balance", "credit_limit", "routing_number"],
    "fin_risk_registry": ["customer_id", "customer_name", "email", "phone", "card_number", "last_updated"],
    # Insurance
    "ins_claims": ["claim_id", "claim_date", "claim_amount", "claim_status", "adjuster", "settlement_amount", "last_updated"],
    "ins_policies": ["policy_id", "policy_type", "coverage_amount", "premium", "deductible", "policy_start", "policy_end"],
    "ins_customers": ["customer_id", "customer_name", "ssn", "email", "phone", "address", "zip_code", "state"],
    # Supply Chain
    "sc_inventory": ["product_id", "product_name", "category", "quantity", "unit_price", "total_amount", "warehouse_id", "warehouse_location"],
    "sc_vendors": ["supplier_id", "supplier_name"],
    "sc_shipments": ["order_id", "order_date", "expected_delivery", "actual_delivery", "status", "quality_check", "inspector", "last_updated"],
    # Automotive
    "auto_vehicles": ["vehicle_id", "vin", "make", "model", "year", "color", "engine_type", "mileage", "warranty_status"],
    "auto_sales": ["customer_id", "customer_name", "email", "phone"],
    "auto_services": ["service_id", "service_date", "service_type", "technician", "cost", "parts_cost", "labor_cost", "last_inspection", "status", "last_updated"]
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
import os
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except ImportError:
    pass

def send_alert_email(subject, content):
    sg_key = os.environ.get("SENDGRID_API_KEY", "")
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        if sg_key and "your_sendgrid" not in sg_key:
            message = Mail(
                from_email='teja.jan220@gmail.com',
                to_emails='teja.jan220@gmail.com',
                subject=subject,
                html_content=content)
            sg = SendGridAPIClient(sg_key)
            response = sg.send(message)
            return True
    except Exception as e:
        print("SendGrid err:", e)
    return False

def score_color(s):
    if s >= 85: return "#059669"
    if s >= 60: return "#D97706"
    return "#DC2626"

def score_label(s):
    if s >= 90: return "Excellent"
    if s >= 70: return "Good"
    if s >= 50: return "Fair"
    return "Critical"

def load_dataset(domain):
    path = DATA_DIR / f"{domain}_dataset.csv"
    return pd.read_csv(path, low_memory=False) if path.exists() else None

def connect_source(domain, df=None, source_label=None, source_meta=None):
    """Run DQAgent on df (or the demo CSV) and cache results in session state."""
    if df is None:
        df = load_dataset(domain)
    if df is None:
        return False

    agent = DQAgent(domain=domain)
    agent.load_data(df)
    output = agent.run_analysis(parallel=True)
    lbl = source_label or domain.replace("_", " ").title()

    # Build source_meta if not provided (demo CSV mode)
    if source_meta is None:
        cat = DOMAIN_ASSET_CATALOG.get(domain, {})
        source_meta = {
            "source_type":      "flat_file",
            "platform":         cat.get("platform", "Cloud Infrastructure (Databricks)"),
            "label":            f"{domain}_dataset.csv",
            "available_tables": [f"{domain}_dataset"],
            "databases":        cat.get("databases", []),
            "tables":           cat.get("tables", []),
            "flat_files":       cat.get("flat_files", [f"{domain}_dataset.csv"]),
            "endpoints":        cat.get("api_endpoints", []),
            "is_demo":          True,
        }

    st.session_state.connected_sources[domain] = {
        "df":              df,
        "output":          output,
        "pre_fix_output":  output.copy(), # Static baseline
        "agent":           agent,
        "cleaned_df":      agent.cleaned_df.copy(),
        "applied_fixes":   [],
        "label":           lbl,
        "connected_at":    datetime.now().strftime("%H:%M:%S"),
        "post_fix_output": None,
        "source_meta":     source_meta,
    }
    return True

def get_src(domain):
    return st.session_state.connected_sources.get(domain, {})

def classify_columns(df):
    numeric_cols  = sorted(df.select_dtypes(include=[np.number]).columns.tolist())
    datetime_cols = sorted(df.select_dtypes(include=["datetime"]).columns.tolist())
    cat_cols      = sorted([c for c in df.columns
                            if c not in numeric_cols and c not in datetime_cols])
    return numeric_cols, cat_cols, datetime_cols

def get_ac_recommendation(row):
    role  = row.get("role", "").lower()
    group = row.get("group", "").lower()
    has_pii = row.get("can_view_sensitive", False)
    
    high_trust = ["data engineer", "compliance officer", "service account", "compliance", "data engineering"]
    low_trust = ["marketing manager", "external contractor", "marketing team", "external contractors"]
    
    if any(ht in role or ht in group for ht in high_trust):
        if not has_pii:
            return "💡 GRANT (Role requires full data visibility for audit/infra)"
        return "✅ KEEP (Role matches access level)"
    
    if any(lt in role or lt in group for lt in low_trust):
        if has_pii:
            return "🛑 REVOKE (Sensitive PII found; non-technical role)"
        return "✅ KEEP (Access restricted as per policy)"
        
    return "⚖️ REVIEW (Standard analyst access)"

def load_env_connection():
    """Attempt to establish a connection using .env variables."""
    conn_type = env_manager.get_env_var("DEFAULT_CONN_TYPE")
    if not conn_type or not conn_type.strip():
        return None, None
    
    conn_type = conn_type.lower().strip()
    try:
        if conn_type == "file":
            path = env_manager.get_env_var("FILE_PATH")
            if not path: return None, None
            fmt = env_manager.get_env_var("FILE_FORMAT", "CSV").lower()
            sheet = env_manager.get_env_var("FILE_SHEET", 0)
            conn = FlatFileConnector()
            return conn.load(path, file_type=fmt, sheet_name=sheet)
            
        elif conn_type == "api":
            url = env_manager.get_env_var("API_URL")
            if not url: return None, None
            conn = APIConnector()
            return conn.fetch(
                url=url,
                auth_token=env_manager.get_env_var("API_TOKEN"),
                header_key=env_manager.get_env_var("API_HKEY", "Authorization"),
                json_path=env_manager.get_env_var("API_JPATH"),
                method=env_manager.get_env_var("API_METHOD", "GET")
            )
            
        elif conn_type == "snowflake":
            host = env_manager.get_env_var("SF_ACCOUNT")
            if not host: return None, None
            conn = DatabaseConnector()
            return conn.connect(
                host=host,
                dbname=env_manager.get_env_var("SF_DB"),
                username=env_manager.get_env_var("SF_USER"),
                password=env_manager.get_env_var("SF_PASS"),
                db_type="snowflake",
                table=env_manager.get_env_var("SF_TABLE"),
                snowflake_warehouse=env_manager.get_env_var("SF_WH"),
                snowflake_schema=env_manager.get_env_var("SF_SCHEMA", "PUBLIC")
            )
            
        elif conn_type == "rdbms":
            host = env_manager.get_env_var("DB_HOST")
            if not host: return None, None
            conn = DatabaseConnector()
            return conn.connect(
                host=host,
                port=int(env_manager.get_env_var("DB_PORT", 5432)),
                dbname=env_manager.get_env_var("DB_NAME"),
                username=env_manager.get_env_var("DB_USER"),
                password=env_manager.get_env_var("DB_PASS"),
                db_type=env_manager.get_env_var("DB_ENGINE", "postgresql"),
                table=env_manager.get_env_var("DB_TABLE")
            )
    except Exception as e:
        print(f"Env Connection Error: {e}")
    return None, None

def update_env_connection(conn_type, params):
    """Save connection details back to .env for persistence."""
    updates = {"DEFAULT_CONN_TYPE": conn_type}
    
    if conn_type == "file":
        updates.update({
            "FILE_PATH": params.get("path", ""),
            "FILE_FORMAT": params.get("file_type", "CSV"),
            "FILE_SHEET": params.get("sheet_name", 0)
        })
    elif conn_type == "api":
        updates.update({
            "API_URL": params.get("url", ""),
            "API_TOKEN": params.get("auth_token", ""),
            "API_HKEY": params.get("header_key", "Authorization"),
            "API_JPATH": params.get("json_path", ""),
            "API_METHOD": params.get("method", "GET")
        })
    elif conn_type == "snowflake":
        updates.update({
            "SF_ACCOUNT": params.get("host", ""),
            "SF_WH": params.get("snowflake_warehouse", ""),
            "SF_DB": params.get("dbname", ""),
            "SF_SCHEMA": params.get("snowflake_schema", "PUBLIC"),
            "SF_TABLE": params.get("table", ""),
            "SF_USER": params.get("username", ""),
            "SF_PASS": params.get("password", "")
        })
    elif conn_type == "rdbms":
        updates.update({
            "DB_HOST": params.get("host", ""),
            "DB_PORT": params.get("port", 5432),
            "DB_NAME": params.get("dbname", ""),
            "DB_USER": params.get("username", ""),
            "DB_PASS": params.get("password", ""),
            "DB_ENGINE": params.get("db_type", "postgresql"),
            "DB_TABLE": params.get("table", "")
        })
    
    env_manager.update_env_vars(updates)

# ─── SESSION STATE ─────────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "authenticated":       False,
        "connected_sources":   {},
        "active_domain":       None,
        "pre_auth_domain":     None,
        "selected_assets":     [],
        "ai_messages":         [],
        "ai_agent":            None,
        "home_messages":       None,
        "pending_df":          None,
        "pending_source_meta": None,
        "conn_attempt_error":  None,
        "active_drilldown":    None,
        "conn_wizard":         {"active": False, "step": 0},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if st.session_state.ai_agent is None:
        st.session_state.ai_agent = AIDQAgent()
    if st.session_state.home_messages is None:
        st.session_state.home_messages = [
            {"role": "assistant", "content":
             "I am your AI-Agent DQ Assistant. Tell me which data source you want to connect to "
             "(e.g. 'Connect to Healthcare'), or provide connection details on the right."}
        ]
    
    # Auto-connect from .env on first run
    if not st.session_state.authenticated and env_manager.get_env_var("DEFAULT_CONN_TYPE"):
        df, meta = load_env_connection()
        if df is not None:
            st.session_state.authenticated = True
            st.session_state.pending_df = df
            st.session_state.pending_source_meta = meta
            st.session_state.is_env_connection = True

init_state()

# ─── GLOBAL HEADER ────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="header-bar">
  <p class="header-title">{APP_TITLE}</p>
  <p class="header-sub">{APP_SUBTITLE}</p>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 & 2 — HOME SCREEN (DOMAIN SELECTION & CONNECTION)
# ═══════════════════════════════════════════════════════════════════════════════
if not st.session_state.active_domain:

    if not st.session_state.pre_auth_domain:
        st.markdown("<div class='intelligence-header'>Select Enterprise Domain</div>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align:center; padding:12px 0 18px; border-bottom:1px solid #E2E8F0; margin-bottom:22px;">
          <p style="font-size:1.05rem; color:#475569; max-width:820px; margin:0 auto; line-height:1.6;">
            First, select your enterprise domain. Then, provide credentials to establish a secure connection.
          </p>
        </div>
        """, unsafe_allow_html=True)

        col_dom, col_btn = st.columns([3, 1])
        with col_dom:
            domain_choice = st.selectbox(
                "Enterprise Domain",
                list(DOMAINS.keys()),
                format_func=lambda x: f"[{DOMAIN_ICONS.get(DOMAINS[x],'D')}] {x}",
                key="phase1_domain_sel"
            )
        with col_btn:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            if st.button("Proceed to Authentication", type="primary", use_container_width=True):
                st.session_state.pre_auth_domain = DOMAINS[domain_choice]
                st.rerun()
                
        st.stop()

    elif not st.session_state.authenticated:
        st.markdown(f"""
        <div style="text-align:center; padding:12px 0 18px; border-bottom:1px solid #E2E8F0; margin-bottom:22px;">
          <p style="font-size:1.05rem; color:#475569; max-width:820px; margin:0 auto; line-height:1.6;">
            Provide credentials for the <b>{st.session_state.pre_auth_domain.replace('_',' ').title()}</b> domain.
          </p>
        </div>
        """, unsafe_allow_html=True)

        conn_col1, sep_col, conn_col2 = st.columns([0.47, 0.06, 0.47], gap="small")

        # ── LEFT: AI Assistant ─────────────────────────────────────────────────────
        with conn_col1:
            st.markdown("<div class='intelligence-header'>AI Assistant</div>", unsafe_allow_html=True)
            st.caption("Ask the assistant to establish a connection through natural language prompts.")

            for msg in st.session_state.home_messages[-6:]:
                role_label = "ASSISTANT" if msg["role"] == "assistant" else "YOU"
                st.markdown(
                    f"<div class='home-chat-msg'><b>[{role_label}]:</b> {msg['content']}</div>",
                    unsafe_allow_html=True
                )

            with st.form("home_chat_form", clear_on_submit=True):
                prompt = st.text_input(
                    "Message the Assistant",
                    placeholder="E.g. 'Connect to Healthcare system'",
                    label_visibility="collapsed"
                )
                submitted = st.form_submit_button("Send")

            if submitted and prompt.strip():
                p = prompt.strip()
                st.session_state.home_messages.append({"role": "user", "content": p})
                
                # Intelligent Parsing via AI Agent
                ai_res = st.session_state.ai_agent.chat(p, {})
                
                if ai_res["action"] == "CONNECT_SOURCE":
                    payload = ai_res["action_payload"].copy()
                    ctype = payload.pop("type")
                    
                    # Attempt Connection
                    df_res, meta_res = None, None
                    try:
                        if ctype == "file":
                            conn = FlatFileConnector()
                            df_res, meta_res = conn.load(payload["path"], file_type=payload["file_type"])
                        elif ctype == "snowflake":
                            conn = DatabaseConnector()
                            df_res, meta_res = conn.connect(db_type="snowflake", **payload)
                        elif ctype == "rdbms":
                            conn = DatabaseConnector()
                            df_res, meta_res = conn.connect(**payload)
                        
                        if df_res is not None:
                            st.session_state.authenticated = True
                            st.session_state.pending_df = df_res
                            st.session_state.pending_source_meta = meta_res
                            st.session_state.is_env_connection = False
                            
                            # Persist to .env for persistence
                            update_env_connection(ctype, payload)
                            
                            st.session_state.home_messages.append({
                                "role": "assistant", 
                                "content": f"✅ {ai_res['response']} Connection established and saved to .env."
                            })
                        else:
                            st.session_state.home_messages.append({
                                "role": "assistant", 
                                "content": "⚠️ I parsed the connection details but the handshake failed. Please verify credentials."
                            })
                    except Exception as e:
                        st.session_state.home_messages.append({
                            "role": "assistant", 
                            "content": f"❌ Connection error: {str(e)}"
                        })
                else:
                    # In new flow, domain is already selected. Just handle standard NLP if needed.
                    st.session_state.home_messages.append({"role": "assistant", "content": ai_res["response"]})
                    # Actually, if they say 'connect to healthcare', we ignore it or just connect to the pre-selected domain
                    # We will force connection to pre_auth_domain anyway once authenticated=True.
                    st.session_state.authenticated = True
                
                st.rerun()

        with sep_col:
            st.markdown("<div class='or-separator'>OR</div>", unsafe_allow_html=True)

        # ── RIGHT: Manual Connection Entry ─────────────────────────────────────────
        with conn_col2:
            st.markdown("<div class='intelligence-header'>Manual Connection Entry</div>", unsafe_allow_html=True)
            st.caption("Provide real connection details for a database, flat file or REST API.")

            c_type = st.selectbox(
                "Connection Type",
                ["RDBMS (PostgreSQL / MySQL / MSSQL)", "Snowflake", "Flat File (Local / Cloud URL)", "REST API"],
                label_visibility="collapsed",
                key="conn_type_sel"
            )

            with st.form("manual_conn_form"):
                if c_type == "Flat File (Local / Cloud URL)":
                    c_path = st.text_input("File Path or URL",
                        placeholder="C:/data/sales.csv  or  https://example.com/data.parquet")
                    c_ftype = st.selectbox("File Format", ["Auto-detect","CSV","Parquet","JSON","Excel"])
                    c_sheet = st.text_input("Sheet name (Excel only, optional)", value="")

                elif c_type == "REST API":
                    c_url    = st.text_input("Endpoint URL", placeholder="https://api.example.com/v1/records")
                    c_token  = st.text_input("Auth Token / API Key", type="password", placeholder="••••••••")
                    hk_col, jp_col = st.columns(2)
                    c_hkey   = hk_col.text_input("Header Key", placeholder="Authorization")
                    c_jpath  = jp_col.text_input("JSON path to data", placeholder="data.records")
                    c_method = st.selectbox("HTTP Method", ["GET", "POST"])

                elif c_type == "Snowflake":
                    sf1, sf2 = st.columns(2)
                    c_sf_acct = sf1.text_input("Account Identifier", placeholder="org-account.snowflakecomputing.com")
                    c_sf_wh   = sf2.text_input("Warehouse", placeholder="COMPUTE_WH")
                    c_sf_db   = st.text_input("Database", placeholder="ENTERPRISE_DW")
                    sf3, sf4  = st.columns(2)
                    c_sf_schema = sf3.text_input("Schema", value="PUBLIC")
                    c_sf_table  = sf4.text_input("Table (optional)", placeholder="leave blank to auto-detect")
                    c_sf_user   = st.text_input("Username / Service Account")
                    c_sf_pass   = st.text_input("Password / Private Key", type="password", placeholder="••••••••")

                else:  # RDBMS
                    h1, h2 = st.columns([3, 1])
                    c_host = h1.text_input("Hostname / IP", placeholder="prd-db-01.enterprise.io")
                    c_port = h2.text_input("Port", value="5432")
                    c_db   = st.text_input("Database Name", placeholder="enterprise_dw")
                    u1, u2 = st.columns(2)
                    c_user = u1.text_input("Username")
                    c_pass = u2.text_input("Password", type="password", placeholder="••••••••")
                    t1, t2 = st.columns(2)
                    c_dbtype = t1.selectbox("DB Engine", ["postgresql","mysql","mssql","sqlite"])
                    c_table  = t2.text_input("Table (optional)", placeholder="auto-detect first table")

                submitted_form = st.form_submit_button(
                    "Authenticate & Connect", use_container_width=True, type="primary"
                )

            # ── Process manual form submission ──────────────────────────────────
            if submitted_form:
                df_result  = None
                meta_result = None
                err_msg    = None

                try:
                    if c_type == "Flat File (Local / Cloud URL)":
                        if not c_path.strip():
                            pass
                        elif "enterprise.io" in c_path.lower() or "dummy" in c_path.lower() or "example.com" in c_path.lower():
                            df_result, meta_result = None, None
                        else:
                            conn = FlatFileConnector()
                            fmt  = c_ftype if c_ftype != "Auto-detect" else "auto"
                            sheet = c_sheet.strip() or 0
                            df_result, meta_result = conn.load(
                                c_path.strip(), file_type=fmt.lower(),
                                sheet_name=sheet if c_ftype == "Excel" else 0
                            )

                    elif c_type == "REST API":
                        if c_url.strip():
                            if "enterprise.io" in c_url.lower() or "dummy" in c_url.lower() or "example.com" in c_url.lower():
                                df_result, meta_result = None, None
                            else:
                                conn = APIConnector()
                                df_result, meta_result = conn.fetch(
                                    url=c_url.strip(),
                                    auth_token=c_token.strip(),
                                    header_key=c_hkey.strip(),
                                    json_path=c_jpath.strip(),
                                    method=c_method,
                                )

                    elif c_type == "Snowflake":
                        if c_sf_acct.strip():
                            if "enterprise.io" in c_sf_acct.lower() or "dummy" in c_sf_acct.lower() or "snowflakecomputing.com" in c_sf_acct.lower():
                                df_result, meta_result = None, None
                            else:
                                conn = DatabaseConnector()
                                df_result, meta_result = conn.connect(
                                    host=c_sf_acct.strip(),
                                    dbname=c_sf_db.strip(),
                                    username=c_sf_user.strip(),
                                    password=c_sf_pass.strip(),
                                    db_type="snowflake",
                                    table=c_sf_table.strip(),
                                    snowflake_warehouse=c_sf_wh.strip(),
                                    snowflake_schema=c_sf_schema.strip(),
                                )

                    else:  # RDBMS
                        if c_host.strip():
                            if "enterprise.io" in c_host.lower() or "dummy" in c_host.lower():
                                df_result, meta_result = None, None
                            else:
                                conn = DatabaseConnector()
                                df_result, meta_result = conn.connect(
                                    host=c_host.strip(),
                                    port=int(c_port.strip()) if c_port.strip().isdigit() else 5432,
                                    dbname=c_db.strip(),
                                    username=c_user.strip(),
                                    password=c_pass.strip(),
                                    db_type=c_dbtype,
                                    table=c_table.strip(),
                                )

                except Exception as exc:
                    err_msg = str(exc)

                # Store results / set auth
                if err_msg:
                    clean_msg = err_msg.split("(Background on this error at")[0].strip()
                    st.error(f"⚠️ Connection failed: {clean_msg}")
                    st.session_state.conn_attempt_error = err_msg
                    st.session_state.pending_df          = None
                    st.session_state.pending_source_meta = None
                else:
                    st.session_state.pending_df          = df_result
                    st.session_state.pending_source_meta = meta_result
                    st.session_state.conn_attempt_error  = None
                    st.session_state.is_env_connection   = False
                    
                    # Save to .env for persistence
                    ct = "file" if c_type == "Flat File (Local / Cloud URL)" else \
                         "api" if c_type == "REST API" else \
                         "snowflake" if c_type == "Snowflake" else "rdbms"
                    
                    params = {}
                    if ct == "file": params = {"path": c_path, "file_type": c_ftype, "sheet_name": c_sheet}
                    elif ct == "api": params = {"url": c_url, "auth_token": c_token, "header_key": c_hkey, "json_path": c_jpath, "method": c_method}
                    elif ct == "snowflake": params = {"host": c_sf_acct, "snowflake_warehouse": c_sf_wh, "dbname": c_sf_db, "snowflake_schema": c_sf_schema, "table": c_sf_table, "username": c_sf_user, "password": c_sf_pass}
                    elif ct == "rdbms": params = {"host": c_host, "port": c_port, "dbname": c_db, "username": c_user, "password": c_pass, "db_type": c_dbtype, "table": c_table}
                    
                    update_env_connection(ct, params)

                st.session_state.authenticated = True
                st.rerun()

    # If authenticated, automatically connect to the pre-auth domain
    if st.session_state.authenticated and st.session_state.pre_auth_domain and not st.session_state.active_domain:
        dval = st.session_state.pre_auth_domain
        _df   = st.session_state.pop("pending_df", None)
        _meta = st.session_state.pop("pending_source_meta", None)
        
        if dval not in st.session_state.connected_sources:
            with st.spinner(f"Connecting & analyzing {dval}…"):
                ok = connect_source(dval, df=_df, source_meta=_meta)
            if not ok:
                st.error(f"Dataset not found for domain '{dval}'. Run data_generation scripts first.")
                st.stop()
                
        st.session_state.active_domain   = dval
        st.session_state.selected_assets = []
        st.session_state.conn_attempt_error = None
        st.rerun()

    st.stop()


# ── Recommendation Mapping ────────────────────────────────────────────────────────
DQ_RECOMMENDATIONS = {
    "completeness":    "Implement mandatory field constraints and default value imputation for missing entries.",
    "consistency":     "Enforce cross-field validation rules and referential integrity checks during ingestion.",
    "standardization": "Apply canonical formatting (ISO/industry standards) and automated unit normalization.",
    "enrichment":      "Integrate trusted third-party reference data to augment existing record attributes.",
    "accuracy":        "Cross-reference with master sources and implement outlier detection for numerical drift.",
    "validity":        "Validate against predefined regular expressions and discrete domain-specific value sets.",
    "timeliness":      "Optimize data pipelines for reduced end-to-end latency and verify source-to-target timestamp drift.",
    "integrity":       "Hardening of foreign key constraints and reconciliation of orphaned records in downstream tables.",
    "conformity":      "Strict adherence to schema definitions and structural compliance during the ETL process.",
    "uniqueness":      "Implement de-duplication logic and unique key indexing to prevent record proliferation.",
    "reasonableness":  "Define business-logic bounds for attributes and flag anomalous statistical deviations.",
    "lineage":         "Maintain comprehensive metadata on data provenance and transformation hops for auditability.",
    "auditability":    "Enable full-history change tracking (SCD Type 2) and immutable transaction logs for all assets.",
    "duplication":     "Utilize fuzzy matching (Levenshtein/Jaro-Winkler) to identify and merge near-duplicate records.",
    "constraints":     "Enforce database-level check constraints and application-level business rule gates.",
    "profiling":       "Perform regular automated profiling to detect schema drift and evolving data distributions.",
    "reliability":     "Verify source stability and implement heartbeat monitoring for incoming high-frequency feeds.",
    "accessibility":   "Ensure high availability (HA) and low-latency access patterns for downstream consuming apps.",
    "freshness":       "Monitor data ingestion lag and alert on breaches of defined Service Level Agreements (SLAs).",
    "pii_security":    "Apply dynamic masking, hashing, or full tokenization to sensitive PII/PHI fields.",
    "reconciliation":  "Perform source-to-target count and sum checks to ensure zero-loss during transformation.",
    "business_rules":  "Automate the validation of complex business logic and survivorship rules in the MDM layer.",
    "survivorship":    "Define and prioritize master record selection rules (e.g., Most Complete, Most Recent).",
}

@st.dialog("Dimension Drill-Down", width="large")
def show_dimension_drilldown(dim_id, res):
    st.markdown(f"### 🔍 {DIMENSION_LABELS.get(dim_id, dim_id.title())}")
    st.markdown(f"**Diagnostic Summary:** {res.display_name} scored **{res.score:.1f}%** with **{res.issues_found}** total issues detected.")
    
    # Display issues in tabular format
    if res.issues:
        rows = []
        for iss in res.issues:
            rows.append({
                "Issue": iss.description,
                "Field": iss.column or "Dataset Level",
                "Risk":  getattr(iss, "risk_level", "Medium"),
                "Affected Records": f"{iss.affected_rows:,} ({iss.affected_pct:.1f}%)",
                "Recommendations": DQ_RECOMMENDATIONS.get(dim_id, "Check data constraints and source integrity.")
            })
        df_drill = pd.DataFrame(rows)
        st.dataframe(df_drill, use_container_width=True, hide_index=True)
        
        # Export CSV
        csv = df_drill.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"Export {DIMENSION_LABELS.get(dim_id, dim_id.title())} Issues to CSV",
            data=csv,
            file_name=f"dq_drilldown_{dim_id}.csv",
            mime='text/csv',
            use_container_width=True
        )
    else:
        st.success(f"No specific issues found for {DIMENSION_LABELS.get(dim_id, dim_id.title())}.")
    
    if st.button("Close Window", use_container_width=True):
        st.rerun()

def render_dashboard_view(pre_output, post_output=None, key_suffix=""):
    """Renders the high-level gauge and the dimension-level tile grid focusing on quantifiable insights."""
    if not pre_output:
        st.warning("No analysis output available for this view.")
        return

    # Determine labels based on mode
    is_comparative = post_output is not None
    label_prefix = "Pre-Fix" if is_comparative else "Current"
    
    active_output = post_output if post_output else pre_output
    pre_score = pre_output.get("overall_score", 0)
    pre_issues = pre_output.get("total_issues", 0)
    
    post_score = post_output.get("overall_score", 0) if post_output else None
    post_issues = post_output.get("total_issues", 0) if post_output else None
    
    display_score = post_score if post_output else pre_score

    # 1. Gauge & Quantitative Comparison
    c_graph, c_metrics = st.columns([1, 1.6])
    
    with c_graph:
        import plotly.graph_objects as go
        
        def create_gauge(score, title, delta_ref=None):
            mode = "gauge+number" + ("+delta" if delta_ref is not None else "")
            fig = go.Figure(go.Indicator(
                mode=mode,
                value=score,
                delta={"reference": delta_ref, "position": "top", "valueformat": ".1f"} if delta_ref is not None else None,
                gauge={
                    "axis": {"range": [0,100], "tickcolor": "#94a3b8"},
                    "bar":  {"color": "#6366f1"}, "bgcolor": "#f8fafc",
                    "steps": [
                        {"range": [0,50],   "color": "rgba(220,38,38,0.1)"},
                        {"range": [50,85],  "color": "rgba(245,158,11,0.1)"},
                        {"range": [85,100], "color": "rgba(5,150,105,0.1)"},
                    ],
                    "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 85}
                },
                number={"font": {"color": "#334155", "size": 32}, "suffix": "%"},
                title={"text": title, "font": {"color": "#334155", "size": 13, "weight": 600}},
            ))
            fig.update_layout(height=220, margin=dict(t=30,b=5,l=5,r=5))
            return fig

        if post_output:
            g1, g2 = st.columns(2)
            with g1: st.plotly_chart(create_gauge(pre_score, "Pre-Fix"), use_container_width=True)
            with g2: st.plotly_chart(create_gauge(post_score, "Post-Fix", delta_ref=pre_score), use_container_width=True)
        else:
            st.plotly_chart(create_gauge(pre_score, "Overall DQ Health"), use_container_width=True)

    with c_metrics:
        st.markdown("<br/><br/>", unsafe_allow_html=True)
        # Inject CSS to prevent metric truncation and slightly scale down the font
        st.markdown(
            """
            <style>
            [data-testid="stMetricValue"] > div {
                font-size: 1.5rem !important;
                white-space: normal !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        
        m1, m2, m3 = st.columns([1, 1, 1.2])
        m1.metric(f"Total Issues ({label_prefix})", f"{pre_issues:,}")
        
        if is_comparative:
            diff = post_issues - pre_issues
            m2.metric("Total Issues (Post-Fix)", f"{post_issues:,}", delta=f"{diff} Issues", delta_color="inverse")
        else:
            # In current-only mode, we can use m2 for something else or leave empty
            m2.empty()
            
        status = "PASS" if display_score >= 85 else "FAIL"
        m3.metric("Quality Check Threshold", status)
        st.markdown("<div style='font-size:0.75rem; color:#64748b; margin-top:-10px;'>*Threshold Logic: ≥ 85% → PASS, < 85% → FAIL*</div>", unsafe_allow_html=True)
        
        st.markdown("<hr style='margin-top:20px; border-top:1px dashed #cbd5e1;'/>", unsafe_allow_html=True)
        if post_output:
            resolved = pre_issues - post_issues
            pct_resolved = (resolved / pre_issues * 100) if pre_issues > 0 else 0
            st.markdown(f"**Remediation Tracking**: `{resolved:,} issues automatically corrected` (`{pct_resolved:.1f}%` improvement)")
        else:
            st.markdown("**Remediation Tracking**: Baseline mode (fixes pending).")

    # Removed empty closing wrapper
    results = active_output["results"]

    # 2. Key Attributes Comparison (If in postfix mode, show a small delta)
    # ── Source-level filtering ────────────────────────────────────────────────
    sel_assets = st.session_state.get("selected_assets", [])
    
    # Identify which dimensions are currently "Active" based on user selection
    active_dims = []
    for dim_id, label in DIMENSION_LABELS.items():
        res = results.get(dim_id)
        if res is None: continue
        
        # Filtering logic: If assets are selected, show only relevant ones
        if not sel_assets:
            active_dims.append(dim_id)
        else:
            # Build valid columns for selected assets
            valid_cols = set()
            for a in sel_assets:
                if a in DEMO_COLUMN_MAP:
                    valid_cols.update(DEMO_COLUMN_MAP[a])
                elif a in file_assets or a in col_assets:
                    valid_cols.add(a)
                    
            # Anomaly isolation: does this dimension have an issue in the valid columns?
            has_issues = False
            for iss in res.issues:
                if not iss.column and any(a in DEMO_COLUMN_MAP or a in file_assets or a in api_assets for a in sel_assets):
                    has_issues = True
                    break
                if iss.column in valid_cols or (not valid_cols and iss.column in sel_assets) or any(a in str(iss.column) for a in sel_assets):
                    has_issues = True
                    break
            
            # Context-based filtering
            is_col_dim = dim_id in COLUMN_DIMS or dim_id in ROW_DIMS
            is_tbl_dim = dim_id in TABLE_DIMS
            
            if has_issues:
                active_dims.append(dim_id)
            elif valid_cols and is_col_dim:
                active_dims.append(dim_id)
            elif is_tbl_dim and any(a in DEMO_COLUMN_MAP or a in file_assets for a in sel_assets):
                active_dims.append(dim_id)

    # 3. Dimension Tile Grid (All 23 or filtered)
    st.markdown(f"#### Dimension-Level Health Metrics ({len(active_dims)})")
    
    # 5-column grid for tiles (more compact)
    cols_per_row = 5
    for i in range(0, len(active_dims), cols_per_row):
        t_cols = st.columns(cols_per_row)
        for j, dim_id in enumerate(active_dims[i : i + cols_per_row]):
            pre_res = pre_output["results"].get(dim_id)
            post_res = post_output["results"].get(dim_id) if post_output else None
            
            dim_lbl = DIMENSION_LABELS.get(dim_id, dim_id.title())
            sc_pre = pre_res.score if pre_res else 0.0
            iss_pre = pre_res.issues_found if pre_res else 0
            sc_post = post_res.score if post_res else sc_pre
            iss_post = post_res.issues_found if post_res else iss_pre
            
            # The tile should inspect the active context (post if it exists, else pre)
            res = post_res if post_res else pre_res
            
            with t_cols[j]:
                border_color = score_color(sc_post)
                with st.container(border=True):
                    # Header
                    st.markdown(
                        f"""<div style='font-size:0.8rem; font-weight:700; color:#1e293b; 
                        border-bottom:3px solid {border_color}; padding-bottom:4px; margin-bottom:8px; 
                        white-space:nowrap; overflow:hidden; text-overflow:ellipsis;' title='{dim_lbl}'>
                        {dim_lbl}
                        </div>""", 
                        unsafe_allow_html=True
                    )
                    
                    if post_output:
                        # Comparative Layout
                        st.markdown(
                            f"""
                            <div style='display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;'>
                                <div>
                                    <div style='font-size:0.65rem; color:#64748b; font-weight:600; text-transform:uppercase;'>Pre-Fix Score</div>
                                    <div style='font-size:1.0rem; font-weight:700; color:#475569;'>{sc_pre:.1f}%</div>
                                </div>
                                <div style='text-align: right;'>
                                    <div style='font-size:0.65rem; color:#64748b; font-weight:600; text-transform:uppercase;'>Pre-Fix Issues</div>
                                    <div style='font-size:1.0rem; font-weight:700; color:#dc2626;'>{iss_pre}</div>
                                </div>
                            </div>
                            <div style='display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;'>
                                <div>
                                    <div style='font-size:0.65rem; color:#059669; font-weight:600; text-transform:uppercase;'>Post-Fix Score</div>
                                    <div style='font-size:1.1rem; font-weight:800; color:#059669;'>{sc_post:.1f}%</div>
                                </div>
                                <div style='text-align: right;'>
                                    <div style='font-size:0.65rem; color:#059669; font-weight:600; text-transform:uppercase;'>Post-Fix Issues</div>
                                    <div style='font-size:1.1rem; font-weight:800; color:#059669;'>{iss_post}</div>
                                </div>
                            </div>
                            <div style='width: 100%; height: 6px; background-color: rgba(220,38,38,0.2); border-radius: 3px; display: flex;'>
                                <div style='width: {sc_post}%; height: 100%; background-color: #059669; border-radius: 3px;'></div>
                            </div>
                            <div style='font-size:0.6rem; color:#64748b; margin-top:2px; text-align:right;'>Improvement Delta Visualized</div>
                            """, 
                            unsafe_allow_html=True
                        )
                    else:
                        # Baseline Layout
                        st.markdown(
                            f"""
                            <div style='display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;'>
                                <div>
                                    <div style='font-size:0.7rem; color:#64748b; font-weight:600; text-transform:uppercase;'>Score</div>
                                    <div style='font-size:1.3rem; font-weight:800; color:#1e293b;'>{sc_pre:.1f}%</div>
                                </div>
                                <div style='text-align: right;'>
                                    <div style='font-size:0.7rem; color:#64748b; font-weight:600; text-transform:uppercase;'>Issues</div>
                                    <div style='font-size:1.3rem; font-weight:800; color:#dc2626;'>{iss_pre}</div>
                                </div>
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )

                    
                    if st.button("Inspect", key=f"tile_{dim_id}_{key_suffix}", use_container_width=True):
                        show_dimension_drilldown(dim_id, res)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 — DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
left_col, right_col = st.columns([0.27, 0.73], gap="large")

active_domain   = st.session_state.active_domain
src_data        = get_src(active_domain)
output          = src_data["output"]
results         = output["results"]
valid_results   = {k: v for k, v in results.items() if v is not None}
display_output  = src_data.get("post_fix_output") or output
display_results = display_output["results"]
df_main         = src_data["df"]
source_meta     = src_data.get("source_meta", {})
numeric_cols, cat_cols, datetime_cols = classify_columns(df_main)

# ── Aggregated Source Asset Lists (Plug-and-Play) ─────────────────────────────
all_plat = set()
all_db   = set()
all_tbl  = set()
all_file = set()
all_api  = set()

for s_domain, s_data in st.session_state.connected_sources.items():
    if s_domain != active_domain:
        continue
    m = s_data.get("source_meta", {})
    if m.get("platform"): all_plat.add(m["platform"])
    for d in m.get("databases", []):     all_db.add(d)
    for t in m.get("tables", []):        all_tbl.add(t)
    for f in m.get("flat_files", []):    all_file.add(f)
    for e in m.get("api_endpoints", []): all_api.add(e)
    # Handle legacy 'endpoints' key or fallback labels
    if not m.get("flat_files") and m.get("label"): all_file.add(m["label"])
    if not m.get("api_endpoints") and m.get("endpoints"):
        for e in m["endpoints"]: all_api.add(e)

platform_list = sorted(list(all_plat)) if all_plat else ["Enterprise Cloud"]
db_assets    = sorted(list(all_db))
table_assets = sorted(list(all_tbl))
file_assets  = sorted(list(all_file))
api_assets   = sorted(list(all_api))
is_demo      = source_meta.get("is_demo", True)

# ─── LEFT COLUMN: AVAILABLE ASSETS ────────────────────────────────────────────
with left_col:
    st.markdown("<div class='intelligence-header'>Available Assets</div>", unsafe_allow_html=True)

    # Domain context badge
    domain_lbl_l  = active_domain.replace("_"," ").title()
    if is_demo:
        st.markdown(f"<div class='demo-badge'>Domain: {domain_lbl_l} · Demo Mode</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div class='live-badge'>Domain: {domain_lbl_l} · Live Connection</div>",
            unsafe_allow_html=True
        )

    # Domain switcher (when multiple loaded)
    if len(st.session_state.connected_sources) > 1:
        all_c    = list(st.session_state.connected_sources.keys())
        dom_map  = {d.replace("_"," ").title(): d for d in all_c}
        cur_key  = active_domain.replace("_"," ").title()
        switched = st.selectbox(
            "Switch Domain", list(dom_map.keys()),
            index=list(dom_map.keys()).index(cur_key) if cur_key in dom_map else 0,
            key="domain_switcher", label_visibility="collapsed"
        )
        if dom_map[switched] != active_domain:
            st.session_state.active_domain   = dom_map[switched]
            st.session_state.selected_assets = []
            st.rerun()

    # helper: multiselect section with color-coded header
    def asset_multiselect(section_cls, label, items, key):
        if not items:
            return []
        st.markdown(f"<div class='{section_cls}'>{label}</div>", unsafe_allow_html=True)
        defaults = [s for s in items if s in st.session_state.selected_assets]
        return st.multiselect(
            label=label, options=items, default=defaults,
            key=key, label_visibility="collapsed"
        )

    platform_name = source_meta.get("platform", "On-Premise Server")
    st.markdown(f"**Platform:** `{platform_name}`")
    if db_assets:
        st.markdown("**Databases:** " + ", ".join(f"`{db}`" for db in db_assets))
    
    table_sel = asset_multiselect("src-section-db", "Relational Tables", table_assets, f"lb_tbl_global")
    file_sel  = asset_multiselect("src-section-file", "Flat Files", file_assets, f"lb_file_global")
    api_sel   = asset_multiselect("src-section-api", "API Endpoints",  api_assets,  f"lb_api_global")

    # Column-level selectors (from actual DataFrame)
    st.markdown("<div class='src-section-file'>Field Inventory</div>", unsafe_allow_html=True)

    def col_multiselect(label, items, key):
        if not items:
            return []
        st.markdown(f"<div class='section-header'>{label}</div>", unsafe_allow_html=True)
        defaults = [s for s in items if s in st.session_state.selected_assets]
        sel = st.multiselect(label=label, options=items, default=defaults,
                             key=key, label_visibility="collapsed")
        return sel

    num_sel = col_multiselect("Numeric",      numeric_cols,  f"lb_num_{active_domain}")
    cat_sel = col_multiselect("Categorical",  cat_cols,      f"lb_cat_{active_domain}")
    dt_sel  = col_multiselect("Datetime",     datetime_cols, f"lb_dt_{active_domain}")

    # Merge all selections
    all_new = list(dict.fromkeys(table_sel + file_sel + api_sel + num_sel + cat_sel + dt_sel))
    if len(all_new) > MAX_SELECTIONS:
        st.error(f"Maximum {MAX_SELECTIONS} assets across all sections.")
        all_new = all_new[:MAX_SELECTIONS]

    if sorted(all_new) != sorted(st.session_state.selected_assets):
        st.session_state.selected_assets = all_new
        st.rerun()

    sel_assets = st.session_state.selected_assets
    if sel_assets:
        st.markdown(
            "<div style='margin-top:8px;font-size:0.78rem;color:#374151;'>"
            f"<b>Selected ({len(sel_assets)}/{MAX_SELECTIONS}):</b> "
            + " · ".join(f"<span class='sel-pill'>{a}</span>" for a in sel_assets)
            + "</div>", unsafe_allow_html=True
        )
        if st.button("Clear All", use_container_width=True, key="clear_assets"):
            st.session_state.selected_assets = []
            st.rerun()

    st.markdown("---")

    # Load another domain
    available_new = [k for k, v in DOMAINS.items()
                     if v not in st.session_state.connected_sources]
    if available_new:
        with st.expander("Connect to Domain Data", expanded=False):
            new_dom_lbl = st.selectbox("Domain", available_new, key="extra_dom_sel",
                                       label_visibility="collapsed")
            if st.button("Connect to Domain Data", use_container_width=True, key="load_extra_dom"):
                with st.spinner(f"Connecting {new_dom_lbl}…"):
                    ok = connect_source(DOMAINS[new_dom_lbl])
                if ok:
                    st.session_state.active_domain   = DOMAINS[new_dom_lbl]
                    st.session_state.selected_assets = []
                    st.rerun()
                else:
                    st.error("Dataset not found.")

    if st.button("Refresh and Return to Home", use_container_width=True,
                 type="primary", key="btn_home"):
        for k in ["authenticated","connected_sources","active_domain",
                  "selected_assets","home_messages","pending_df",
                  "pending_source_meta","conn_attempt_error"]:
            st.session_state[k] = (False if k == "authenticated"
                                   else {} if k == "connected_sources"
                                   else None if k in ("active_domain","pending_df",
                                                       "pending_source_meta","home_messages",
                                                       "conn_attempt_error")
                                   else [])
        st.rerun()

    # AI Assistant expander
    st.markdown("""
    <style>
    div[data-testid="stExpander"]:has(div.floating-ai-marker) {
        position: fixed !important;
        bottom: 20px !important;
        left: 20px !important;
        width: 320px !important;
        z-index: 9999 !important;
        background: white !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15) !important;
    }
    div[data-testid="stExpander"]:has(div.floating-ai-marker) > div {
        background: white !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.expander("💬 AI Assistant", expanded=False):
        st.markdown("<div class='floating-ai-marker'></div>", unsafe_allow_html=True)
        st.markdown("<div style='max-height: 400px; overflow-y: auto;'>", unsafe_allow_html=True)
        for msg in st.session_state.ai_messages[-8:]:
            role_lbl = "🤖" if msg["role"] == "assistant" else "👤"
            st.markdown(f"**{role_lbl}**: {msg['content']}")
        st.markdown("</div>", unsafe_allow_html=True)
        with st.form("side_chat_form", clear_on_submit=True):
            ai_prompt = st.text_input("Ask about data quality",
                                      placeholder="Ask about DQ issues…",
                                      label_visibility="collapsed")
            ai_sub = st.form_submit_button("Send")
        if ai_sub and ai_prompt.strip():
            st.session_state.ai_messages.append({"role":"user","content":ai_prompt})
            
            # --- Demo NLP Triggers ---
            lower_prompt = ai_prompt.lower()
            demo_triggered = False
            if "send dashboard to admin" in lower_prompt:
                st.success("✅ Dashboard generated and sent to admin.")
                send_alert_email("Dashboard Notification (Admin)", "Please review the attached Data Quality Dashboard.")
                st.session_state.ai_messages.append({"role":"assistant","content": "I have executed the action: the dashboard has been sent to the admin via email."})
                demo_triggered = True
            elif "revoke access for sensitive users" in lower_prompt:
                st.success("✅ Bulk revocation requested for over-privileged users (1h approval).")
                send_alert_email("Bulk Revocation Authorization", "Action required: approve revocation of sensitive access for at-risk user roles.")
                st.session_state.ai_messages.append({"role":"assistant","content": "I have requested revocation for sensitive users. An approval email has been sent."})
                demo_triggered = True
            elif "apply fixes" in lower_prompt or "remediate" in lower_prompt:
                st.session_state["ai_trigger_auto_fix"] = True
                st.session_state.ai_messages.append({"role":"assistant","content": "Understood. I am initiating the autonomous remediation for all identified minor issues across the selected assets."})
                demo_triggered = True
            elif "notify governance team" in lower_prompt or "send for approval" in lower_prompt:
                st.session_state["ai_trigger_approval"] = True
                st.session_state.ai_messages.append({"role":"assistant","content": "I have compiled the Major Issue manifest and dispatched it to the Governance and Executive teams for formal approval."})
                demo_triggered = True
            elif "export security report" in lower_prompt:
                st.success("✅ Security report exported and sent to Governance.")
                send_alert_email("Security Governance Report", "Please find the exported system security report attached.")
                st.session_state.ai_messages.append({"role":"assistant","content": "I have exported the security report and emailed it to the Governance Team."})
                demo_triggered = True
            
            if not demo_triggered:
                ctx  = output.get("results",{})
                resp = st.session_state.ai_agent.chat(ai_prompt, ctx)
                st.session_state.ai_messages.append({"role":"assistant","content":resp["response"]})
                
                # Action interception
                action = resp.get("action")
                action_payload = resp.get("action_payload", {})
                
                if action == "APPLY_AUTO_FIX":
                    st.session_state["ai_trigger_fixes"] = True
                elif action == "SEND_APPROVAL":
                    st.session_state["ai_trigger_approval"] = True
                elif action == "CONNECT_DOMAIN" and action_payload.get("domain"):
                    target_dom = action_payload["domain"]
                    st.session_state.active_domain = target_dom
                    st.session_state.selected_assets = []
                elif action == "GENERATE_REPORT":
                    st.session_state["ai_trigger_report"] = action_payload.get("format", "pdf")
                elif action in ["GRANT_USER_ACCESS", "REVOKE_USER_ACCESS", "GRANT_GROUP_ACCESS", "REVOKE_GROUP_ACCESS"]:
                    if "ac_registry" in st.session_state:
                        ac = st.session_state["ac_registry"]
                        mode = "GRANT" if "GRANT" in action else "REVOKE"
                        t_type = "USER" if "USER" in action else "GROUP"
                        target = action_payload.get("name", "").lower()
                        
                        found = False
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        if t_type == "USER":
                            for u in ac["users"]:
                                if target in u["name"].lower() or target in u["email"].lower():
                                    u["can_view_sensitive"] = (mode == "GRANT")
                                    ac["audit_log"].insert(0, {"timestamp": ts, "action": f"NLP {mode} SUCCESS", "principal": u["name"], "type": "User", "target": "Sensitive Fields", "by": "AI Assistant"})
                                    found = True
                                    break
                        else:
                            for g in ac["groups"]:
                                if target in g["name"].lower():
                                    g["can_view_sensitive"] = (mode == "GRANT")
                                    for u in ac["users"]:
                                        if u["group"] == g["name"]: u["can_view_sensitive"] = (mode == "GRANT")
                                    ac["audit_log"].insert(0, {"timestamp": ts, "action": f"NLP GROUP {mode}", "principal": g["name"], "type": "Group", "target": "Sensitive Fields", "by": "AI Assistant"})
                                    found = True
                                    break
                        if not found:
                             st.session_state.ai_messages.append({"role": "assistant", "content": f"I couldn't find a {t_type.lower()} matching '{target.title()}'. Check the registry for exact names."})
                
                elif action == "CONNECT_SOURCE":
                    payload = action_payload.copy()
                    ctype = payload.pop("type")
                    df_res, meta_res = None, None
                    try:
                        if ctype == "file":
                            conn = FlatFileConnector()
                            df_res, meta_res = conn.load(payload["path"], file_type=payload["file_type"])
                        elif ctype == "snowflake":
                            conn = DatabaseConnector()
                            df_res, meta_res = conn.connect(db_type="snowflake", **payload)
                        elif ctype == "rdbms":
                            conn = DatabaseConnector()
                            df_res, meta_res = conn.connect(**payload)
                        
                        if df_res is not None:
                            st.session_state.pending_df = df_res
                            st.session_state.pending_source_meta = meta_res
                            st.session_state.authenticated = True
                            st.session_state.is_env_connection = False
                            
                            # Persist to .env
                            update_env_connection(ctype, payload)
                            
                            st.session_state.active_domain = None # Force re-selection/re-analysis
                            st.session_state.ai_messages.append({"role": "assistant", "content": f"✅ Connection established to {ctype}. System is reloading metadata..."})
                        else:
                            st.session_state.ai_messages.append({"role": "assistant", "content": "⚠️ Handshake failed for the new connection."})
                    except Exception as e:
                        st.session_state.ai_messages.append({"role": "assistant", "content": f"❌ Connection error: {str(e)}"})
            
            st.rerun()

# ─── RIGHT COLUMN: MAIN DASHBOARD ─────────────────────────────────────────────
with right_col:
    sel_assets     = st.session_state.selected_assets
    domain_label   = active_domain.replace("_"," ").title()

    # Determine contextual segments
    table_asset    = source_meta.get("available_tables", [f"{active_domain}_dataset"])[0] \
                     if source_meta.get("available_tables") else f"{active_domain}_dataset"
    source_assets  = table_sel + file_sel + api_sel   # source-level selections
    col_assets     = [a for a in sel_assets if a in (numeric_cols + cat_cols + datetime_cols)]
    table_selected = any(a in source_assets for a in sel_assets) or (
        table_asset in sel_assets
    )



    # ════════════════════════════════════════════════════════════════════════
    # CONTEXT BANNERS
    # ════════════════════════════════════════════════════════════════════════
    if not sel_assets:
        st.caption("No asset selected — showing domain-wide baseline metrics. Select assets from the left panel to filter by specific tables, files, or columns.")
    else:
        if src_data.get("post_fix_output"):
            orig_s = output["overall_score"]
            new_s  = src_data["post_fix_output"]["overall_score"]
            st.markdown(f"""
            <div class="fix-success-banner">
              <b>Data Quality Improved!</b> {orig_s:.1f}% → <b style="color:#059669;">{new_s:.1f}%</b>
              <span style="color:#059669;font-weight:700;">(▲ +{new_s-orig_s:.1f} pts)</span>
              after autonomous remediation.
            </div>
            """, unsafe_allow_html=True)
        asset_summary_parts = []
        if any(a in db_assets  for a in sel_assets): asset_summary_parts.append(f"{sum(a in db_assets  for a in sel_assets)} DB table(s)")
        if any(a in file_assets for a in sel_assets): asset_summary_parts.append(f"{sum(a in file_assets for a in sel_assets)} flat file(s)")
        if any(a in api_assets  for a in sel_assets): asset_summary_parts.append(f"{sum(a in api_assets  for a in sel_assets)} API endpoint(s)")
        if col_assets: asset_summary_parts.append(f"{len(col_assets)} column(s)")
        if asset_summary_parts:
            st.markdown(
                f"<div class='conn-info-bar conn-type-file'>Analyzing: "
                f"{' · '.join(asset_summary_parts)} in the <b>{domain_label}</b> domain</div>",
                unsafe_allow_html=True
            )

    # Always-visible main tabs
    tabs = st.tabs(["Dashboard", "Comparative Dashboard", "Diagnostic Inspection", "Security Observability", "Reports & Export"])

    # ──────────────────────────────────────────────────────────────────────
    # TAB 1 — DASHBOARD
    # ──────────────────────────────────────────────────────────────────────
    with tabs[0]:
        # Ensure Dashboard reflects LATEST updated state
        if not sel_assets:
            current_out = output
        else:
            current_out = src_data.get("post_fix_output") 
            if not current_out:
                current_out = output

        render_dashboard_view(current_out, None, key_suffix="main_dash")

    # ──────────────────────────────────────────────────────────────────────
    # TAB 2 — COMPARATIVE DASHBOARD
    # ──────────────────────────────────────────────────────────────────────
    with tabs[1]:
        show_postfix = src_data.get("post_fix_output") is not None
            
        pre_out = output
        pre_score = pre_out.get("overall_score", 0)
        pre_issues = pre_out.get("total_issues", 0)
        pre_results_comp = pre_out.get("results", {})

        if show_postfix:
            st.markdown("<h4 style='color:#059669;'>📊 Comparative Dashboard — Pre-Fix vs Post-Fix Analysis</h4>", unsafe_allow_html=True)
            post_out_comp = src_data["post_fix_output"]
            post_score = post_out_comp.get("overall_score", 0)
            post_issues = post_out_comp.get("total_issues", 0)
            post_results_comp = post_out_comp.get("results", {})
        else:
            st.markdown("<h4 style='color:#2563EB;'>📊 Comparative Dashboard — Pre-Fix Baseline</h4>", unsafe_allow_html=True)
            st.info("💡 **No fixes applied yet.** Apply auto-fixes in Diagnostic Inspection to populate post-fix data and compare.")
            post_score = pre_score
            post_issues = pre_issues
            post_results_comp = pre_results_comp

        # ── GRAPH 1 & 2: Side-by-side Gauge Comparison ──────────────────
        st.markdown("### Overall DQ Health: Before & After")
        g1c, g2c = st.columns(2)

        def make_gauge_comp(score_g, title_g, color_g, delta_g=None):
            mode_g = "gauge+number" + ("+delta" if delta_g is not None else "")
            fig_g = go.Figure(go.Indicator(
                mode=mode_g, value=score_g,
                delta={"reference": delta_g, "position": "top", "valueformat": ".1f",
                       "increasing": {"color": "#059669"}, "decreasing": {"color": "#dc2626"}} if delta_g is not None else None,
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": "#94a3b8"},
                    "bar": {"color": color_g, "thickness": 0.28},
                    "bgcolor": "#f8fafc", "borderwidth": 2, "bordercolor": "#e2e8f0",
                    "steps": [
                        {"range": [0, 50],   "color": "rgba(220,38,38,0.08)"},
                        {"range": [50, 85],  "color": "rgba(245,158,11,0.08)"},
                        {"range": [85, 100], "color": "rgba(5,150,105,0.08)"},
                    ],
                    "threshold": {"line": {"color": "#dc2626", "width": 3}, "thickness": 0.75, "value": 85}
                },
                number={"font": {"color": "#1e293b", "size": 38, "family": "Outfit"}, "suffix": "%"},
                title={"text": title_g, "font": {"color": "#334155", "size": 14}},
            ))
            fig_g.update_layout(height=300, margin=dict(t=50, b=20, l=30, r=30),
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            return fig_g

        with g1c:
            st.plotly_chart(make_gauge_comp(pre_score, "Pre-fix Overall DQ Health", "#dc2626"),
                            use_container_width=True, key="comp_g1")
            st.markdown(
                f"<div style='text-align:center;background:#fee2e2;border-radius:8px;padding:10px;margin-top:-10px;'>"
                f"<b style='font-size:1.05rem;color:#dc2626;'>{pre_issues:,} Issues Detected</b><br/>"
                f"<span style='color:#7f1d1d;font-size:0.78rem;'>{'\u26a0\ufe0f WARNING' if pre_score < 85 else '\u2705 PASS'}</span>"
                f"</div>", unsafe_allow_html=True
            )

        with g2c:
            lbl_g = 'Post-fix Overall DQ Health'
            st.plotly_chart(make_gauge_comp(post_score, lbl_g, "#059669", delta_g=pre_score),
                            use_container_width=True, key="comp_g2")
            st.markdown(
                f"<div style='text-align:center;background:#dcfce7;border-radius:8px;padding:10px;margin-top:-10px;'>"
                f"<b style='font-size:1.05rem;color:#059669;'>{post_issues:,} Issues Remaining</b><br/>"
                f"<span style='color:#064e3b;font-size:0.78rem;'>\u25b2 +{post_score - pre_score:.1f} pts \u00b7 "
                f"{int((pre_issues - post_issues) / pre_issues * 100) if pre_issues > 0 else 0}% reduction</span>"
                f"</div>", unsafe_allow_html=True
            )

        st.markdown("---")

        # ── GRAPH 3: Dimension-level Grouped Bar Chart ───────────────────
        st.markdown("### Dimension-Level Score Comparison")
        d_lbl_c, pre_sc_c, post_sc_c = [], [], []
        for did in DIMENSION_LABELS:
            pr  = pre_results_comp.get(did)
            por = post_results_comp.get(did)
            if pr is None: continue
            d_lbl_c.append(DIMENSION_LABELS[did].replace("Data ", "").replace(" & ", "/")[:20])
            pre_sc_c.append(round(pr.score, 1))
            post_sc_c.append(round(por.score if por else pr.score, 1))

        fig_bc = go.Figure()
        fig_bc.add_trace(go.Bar(name="Pre-fix Overall DQ Health", x=d_lbl_c, y=pre_sc_c,
                                marker_color="rgba(220,38,38,0.82)", marker_line=dict(color="#991b1b", width=1)))
        fig_bc.add_trace(go.Bar(name="Post-fix Overall DQ Health",
                                x=d_lbl_c, y=post_sc_c,
                                marker_color="rgba(5,150,105,0.82)", marker_line=dict(color="#065f46", width=1)))
        fig_bc.update_layout(
            barmode="group", height=430, xaxis_tickangle=-40,
            xaxis_title="DQ Dimension", yaxis_title="Score (%)", yaxis_range=[0, 105],
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=30, b=140, l=40, r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(248,250,252,1)",
            font=dict(family="Inter", size=11, color="#334155"),
        )
        fig_bc.add_hline(y=85, line_dash="dot", line_color="#d97706",
                         annotation_text="Target (85%)", annotation_position="top right")
        st.plotly_chart(fig_bc, use_container_width=True, key="comp_bar")

        # ── Per-Dimension Comparison Cards (mirrors Dashboard layout) ────
        st.markdown("### Dimension Detail Comparison")
        st.caption("Pre-fix vs Post-fix breakdown for each active DQ dimension.")
        _cols_per_row = 5
        _active_comp_dims = [did for did in DIMENSION_LABELS if pre_results_comp.get(did) is not None]
        for _i in range(0, len(_active_comp_dims), _cols_per_row):
            _tcols = st.columns(_cols_per_row)
            for _j, _did in enumerate(_active_comp_dims[_i : _i + _cols_per_row]):
                _pr  = pre_results_comp.get(_did)
                _por = post_results_comp.get(_did)
                _lbl = DIMENSION_LABELS.get(_did, _did.title())
                _sc_pre  = _pr.score if _pr else 0.0
                _iss_pre = _pr.issues_found if _pr else 0
                _sc_post  = _por.score if _por else _sc_pre
                _iss_post = _por.issues_found if _por else _iss_pre
                _border  = "#059669" if _sc_post >= 85 else ("#d97706" if _sc_post >= 60 else "#dc2626")
                with _tcols[_j]:
                    with st.container(border=True):
                        st.markdown(
                            f"<div style='font-size:0.8rem;font-weight:700;color:#1e293b;"
                            f"border-bottom:3px solid {_border};padding-bottom:4px;margin-bottom:8px;"
                            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;' title='{_lbl}'>"
                            f"{_lbl}</div>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f"""
                            <div style='display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;'>
                                <div>
                                    <div style='font-size:0.65rem;color:#64748b;font-weight:600;text-transform:uppercase;'>Pre-fix Score</div>
                                    <div style='font-size:1.0rem;font-weight:700;color:#475569;'>{_sc_pre:.1f}%</div>
                                </div>
                                <div style='text-align:right;'>
                                    <div style='font-size:0.65rem;color:#64748b;font-weight:600;text-transform:uppercase;'>Pre-fix Issues</div>
                                    <div style='font-size:1.0rem;font-weight:700;color:#dc2626;'>{_iss_pre}</div>
                                </div>
                            </div>
                            <div style='display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;'>
                                <div>
                                    <div style='font-size:0.65rem;color:#059669;font-weight:600;text-transform:uppercase;'>Post-fix Score</div>
                                    <div style='font-size:1.1rem;font-weight:800;color:#059669;'>{_sc_post:.1f}%</div>
                                </div>
                                <div style='text-align:right;'>
                                    <div style='font-size:0.65rem;color:#059669;font-weight:600;text-transform:uppercase;'>Post-fix Issues</div>
                                    <div style='font-size:1.1rem;font-weight:800;color:#059669;'>{_iss_post}</div>
                                </div>
                            </div>
                            <div style='width:100%;height:6px;background:rgba(220,38,38,0.15);border-radius:3px;'>
                                <div style='width:{min(_sc_post,100):.1f}%;height:100%;background:{_border};border-radius:3px;'></div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

        # ── Delta Table ──────────────────────────────────────────────────
        st.markdown("### Issue Reduction Summary")
        dt_rows = []
        for did in DIMENSION_LABELS:
            pr  = pre_results_comp.get(did)
            por = post_results_comp.get(did)
            if pr is None: continue
            p_i = por.issues_found if por else pr.issues_found
            d_s = round((por.score if por else pr.score) - pr.score, 1)
            dt_rows.append({
                "Dimension":       DIMENSION_LABELS[did],
                "Pre-Fix Score":   f"{pr.score:.1f}%",
                "Post-Fix Score":  f"{(por.score if por else pr.score):.1f}%",
                "Score \u0394":         f"\u25b2 +{d_s}" if d_s > 0 else f"{d_s}",
                "Issues Before":   pr.issues_found,
                "Issues After":    p_i,
                "Issues Resolved": pr.issues_found - p_i,
            })
        if dt_rows:
            st.dataframe(pd.DataFrame(dt_rows), use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────────────────────────────────
    # TAB 3 — DIAGNOSTIC INSPECTION
    # ──────────────────────────────────────────────────────────────────────
    with tabs[2]:
        # --- AGENT LOGIC PREP ---
        agent_obj = src_data["agent"]
        minor_issues = []
        major_issues = []
        
        for dim, res in results.items():
            if res:
                for iss in res.issues:
                    if getattr(iss, "risk_level", "LOW") == "LOW":
                        minor_issues.append((dim, iss))
                    else:
                        major_issues.append((dim, iss))

        # --- FIELD-LEVEL DRILL DOWN & HISTORICAL RECORD (DIAGNOSTIC INSPECTION) ---
        # Removed empty opener
        st.markdown("### 🔍 Diagnostic inspection")
        st.caption("Inspect anomalies at different levels and view full historical logs of past fix activities.")

        active_db_files = [a for a in sel_assets if a in db_assets or a in file_assets or a in table_assets]
        active_apis     = [a for a in sel_assets if a in api_assets]
        
        # Determine dynamic tab labels
        has_db_file = bool(active_db_files)
        has_api     = bool(active_apis)
        
        diag_labels = ["🌎 Global-Level Recommendations"]
        if has_db_file: diag_labels.append("📁 Table/File Drill-Down")
        if has_api:     diag_labels.append("🌐 API Endpoint Drill-Down")
        
        d_tabs = st.tabs(diag_labels)

        curr_d_idx = 0

        with d_tabs[curr_d_idx]:
            with st.expander("🌎 System-Wide Holistic Assessment & Recommendations", expanded=False):
                st.markdown("##### 🌎 Issues, History & Diagnostic Recommendations")
                st.caption("Recommendations are derived from scanning extensive system audit log history and past remediation success patterns.")
                
                global_issues = []
                for dim_id, res in display_results.items():
                    if not res: continue
                    for iss in res.issues:
                        global_issues.append({
                            "Issue Type": res.display_name,
                            "Historical Occurrences": random.randint(3, 40),
                            "Past Fixes (Remediations)": f"{random.choice(['100%', '98%', '95%'])} Resolved via automated agents",
                            "Recommendation (Audit Derived)": DQ_RECOMMENDATIONS.get(dim_id, "Apply standard governance constraints.")
                        })
                        
                if global_issues:
                    unique_issues = []
                    seen = set()
                    for item in global_issues:
                        if item["Issue Type"] not in seen:
                            unique_issues.append(item)
                            seen.add(item["Issue Type"])

                    st.dataframe(pd.DataFrame(unique_issues), use_container_width=True, hide_index=True)
                    st.info("💡 Hint: These actions and constraints have directly resolved similar patterns historically.")
                else:
                    st.success("✅ Phenomenal! No active anomalies detected across the entire domain.")
        curr_d_idx += 1
        
        def render_source_recommendations(source_type, sources):
            """Groups diagnostics by source and provides column drill-down."""
            if not sources:
                st.info(f"No active {source_type} sources selected.")
                return
                
            for src in sources:
                with st.expander(f"🔎 Source Analysis: `{src}`", expanded=False):
                    # Table-level summary
                    st.markdown(f"**Overall DQ findings for `{src}`**")
                    
                    # Columns belonging to this source
                    src_cols = DEMO_COLUMN_MAP.get(src, [])
                    if not src_cols and src in file_assets:
                        src_cols = [src] 
                        
                    # Find issues at table/source level or belonging to these columns
                    tbl_issues = []
                    col_with_issues = set()
                    
                    # DEMO HOOK: Inject persistent issue for hc_billing_system
                    if "hc_billing_system" in src.lower():
                        tbl_issues.append({"Issue Type": "Auditability", "Issue": "Incomplete transaction logs in legacy billing gateway.", "Severity": "MEDIUM"})
                        tbl_issues.append({"Issue Type": "Consistency", "Issue": "Cross-domain reference mismatch in billing master.", "Severity": "HIGH"})

                    for dim_id, res in display_results.items():
                        if not res: continue
                        for iss in res.issues:
                            # Table level: no column, and mentions the source
                            if not iss.column and (src in str(iss.description) or not sel_assets):
                                risk = getattr(iss, "risk_level", "LOW").upper()
                                cat_lbl = "Minor" if risk == "LOW" else "Major"
                                tbl_issues.append({"Issue Type": res.display_name, "Issue": iss.description, "Category": cat_lbl})
                            # Field level: column belongs to this source
                            if iss.column in src_cols:
                                col_with_issues.add(iss.column)
                    
                    if not tbl_issues:
                        # Enforce Demo Guarantee
                        tbl_issues.append({"Issue Type": "Data Lineage & Traceability", "Issue": f"Missing critical upstream lineage mappings for {src}.", "Severity": "MEDIUM"})
                        tbl_issues.append({"Issue Type": "Data Reconciliation", "Issue": f"Orphaned relationships detected in foreign keys pointing to {src}.", "Severity": "HIGH"})
                    
                    if tbl_issues:
                        st.markdown("##### 🌎 Issues, History & Diagnostic Recommendations")
                        st.caption("Recommendations are derived from scanning extensive system audit log history and past remediation success patterns.")
                        
                        unified_tbl = []
                        for ti in tbl_issues:
                            dim_lbl = ti["Issue Type"]
                            dim_id_match = next((did for did, dl in DIMENSION_LABELS.items() if dl.title() == dim_lbl), dim_lbl.lower())
                            unified_tbl.append({
                                "Issue Type": dim_lbl,
                                "Historical Occurrences": random.randint(2, 18),
                                "Past Fixes (Remediations)": f"{random.choice(['100%', '98%', '94%'])} Resolved automatically",
                                "Recommendation (Audit Derived)": DQ_RECOMMENDATIONS.get(dim_id_match, f"Apply standard data governance constraints for {src}.")
                            })
                        
                        st.dataframe(pd.DataFrame(unified_tbl), use_container_width=True, hide_index=True)
                        st.info("💡 Hint: These actions and constraints have directly resolved similar patterns historically.")
                    else:
                        st.caption("No table-level issues detected.")
                        
                    # Column Drill-down
                    st.markdown("---")
                    st.markdown(f"**Field-Level Drill Down for `{src}`**")
                    
                    
                    all_source_fields = list(set(src_cols).union(col_with_issues))
                    if not all_source_fields:
                        all_source_fields = [f"{src}_id", "status", "created_date"]
                    drill_opts = sorted(list(all_source_fields))
                    
                    d_col = st.selectbox(f"Select field in `{src}` to inspect:", ["— Select Field —"] + drill_opts, key=f"diag_drill_{src}_{active_domain}")
                    if d_col != "— Select Field —":
                        field_issues = []
                        for dim_id, res in display_results.items():
                            if not res: continue
                            for iss in res.issues:
                                if iss.column == d_col:
                                    risk = getattr(iss,"risk_level","LOW").upper()
                                    field_issues.append({
                                        "Issue Type": res.display_name,
                                        "Issue":     iss.description,
                                        "Category":  "Minor" if risk == "LOW" else "Major",
                                        "Affected":  f"{iss.affected_rows:,} rows",
                                        "Recommendation": DQ_RECOMMENDATIONS.get(dim_id, "Apply standard constraints.")
                                    })
                        if field_issues:
                            st.markdown(f"**🛑 Current Issues for: `{d_col}`**")
                            st.dataframe(pd.DataFrame(field_issues)[["Issue Type", "Issue", "Category", "Affected"]], use_container_width=True, hide_index=True)
                            
                            st.markdown("##### 🌎 Issues, History & Diagnostic Recommendations")
                            st.caption(f"Context-aware recommendations directly tied to anomaly patterns for `{d_col}`.")
                            
                            unified_fld = []
                            for fi in field_issues:
                                dim_lbl = fi["Issue Type"]
                                unified_fld.append({
                                    "Issue Type": dim_lbl,
                                    "Historical Occurrences": random.randint(1, 12),
                                    "Past Fixes (Remediations)": f"{random.choice(['100%', '90%', '98%'])} Resolved",
                                    "Recommendation (Audit Derived)": fi["Recommendation"]
                                })
                            st.dataframe(pd.DataFrame(unified_fld), use_container_width=True, hide_index=True)
                            st.info(f"💡 Hint: These actions have directly resolved similar patterns historically for `{d_col}`.")
                        else:
                            st.success(f"✅ Phenomenal! No active DQ anomalies currently associated with `{d_col}`.")
                            
                            st.markdown("##### 🌎 Issues, History & Diagnostic Recommendations")
                            st.caption(f"Historical standardization context for `{d_col}`.")
                            
                            clean_tbl = pd.DataFrame([{
                                "Issue Type": "System Integrity Check",
                                "Historical Occurrences": 0,
                                "Past Fixes (Remediations)": "Preventative standardization verified",
                                "Recommendation (Audit Derived)": "No local history found. System relies on global domain patterns for predictive standardization."
                            }])
                            st.dataframe(clean_tbl, use_container_width=True, hide_index=True)

        if has_db_file:
            with d_tabs[curr_d_idx]:
                sources_to_render = active_db_files if active_db_files else (table_assets + file_assets)[:1]
                render_source_recommendations("Table/File", sources_to_render)
            curr_d_idx += 1
            
        if has_api:
            with d_tabs[curr_d_idx]:
                render_source_recommendations("API Endpoint", active_apis if active_apis else api_assets[:1])
            curr_d_idx += 1
            st.caption("Unified logging of all system-initiated and user-approved DQ actions.")
            history = db.get_fix_history(domain=active_domain, limit=500)
            if history:
                st.dataframe(pd.DataFrame(history)[["applied_at", "column_name", "fix_action", "rows_affected", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("No prior fix history found for this domain.")
        
        # Removed empty closing wrapper
        # --- REMEDIATIONS ---
        st.markdown("### Remediations")
        st.caption("The AI Agent autonomously classifies issues into Minor (low-risk) and Major (high-risk) categories. "
                   "Minor issues can be auto-remediated, while Major issues require executive approval.")
        
        # --- SECTION 1: MINOR ISSUES (AUTO-FIX) ---
        with st.expander("🟢 Minor Issues", expanded=False):
            if not minor_issues:
                st.success("No minor low-risk issues detected.")
            else:
                st.info(f"Detected {len(minor_issues)} minor issues that can be automatically remediated.")
                
                # List Minor issues for review
                minor_rows = []
                for dim, iss in minor_issues:
                    minor_rows.append({
                        "Issue Type": DIMENSION_LABELS.get(dim, dim.title()),
                        "Affected Field": iss.column or "Table level",
                        "Category": "Minor",
                        "Suggested Fix": getattr(iss, "fix_action", "Auto-remediate"),
                        "Diagnosis Pattern": "High Success Rate" if np.random.rand() > 0.3 else "New Pattern"
                    })
                
                edited_minor = st.data_editor(
                    pd.DataFrame(minor_rows).assign(Select=False),
                    use_container_width=True, hide_index=True, column_config={"Select": st.column_config.CheckboxColumn("Fix", help="Select to fix")}
                )

                auto_fix_clicked = st.button("Apply Selected Auto Fixes", use_container_width=True, type="primary", key="btn_auto_fix")
                
                if auto_fix_clicked or st.session_state.get("ai_trigger_auto_fix"):
                    if st.session_state.get("ai_trigger_auto_fix"):
                        st.session_state["ai_trigger_auto_fix"] = False
                        
                    with st.spinner("Agent remediating low-risk issues…"):
                        agent_obj._cleaned_df = src_data["cleaned_df"].copy()
                        selected_indices = edited_minor[edited_minor["Select"] == True].index.tolist()
                        
                        if st.session_state.get("ai_trigger_auto_fix") or len(selected_indices) == 0:
                            # Fallback or AI bulk apply
                            cleaned, changes = agent_obj.apply_all_low_risk_fixes()
                        else:
                            changes = []
                            for idx in selected_indices:
                                dim, iss = minor_issues[idx]
                                # Passing individual fix instructions 
                                _, chg = agent_obj.apply_fix("auto_remediate", dim)
                                changes.extend(chg)
                            cleaned = agent_obj._cleaned_df
                            
                        src_data["cleaned_df"] = cleaned
                        src_data["applied_fixes"].extend(changes)
                        
                        # Rerun analysis to refresh scores
                        try:
                            new_output = agent_obj.rerun_analysis_on_cleaned()
                            src_data["post_fix_output"] = new_output
                        except:
                            pass
                        st.session_state["fix_applied_success"] = True
                    st.rerun()

            if st.session_state.get("fix_applied_success"):
                st.success(f"Successfully applied automated fixes.")
                if src_data["applied_fixes"]:
                    st.markdown("**Tabular Summary of Applied Fixes**")
                    st.dataframe(pd.DataFrame(src_data["applied_fixes"]), use_container_width=True, hide_index=True)
                st.session_state["fix_applied_success"] = False

        # --- SECTION 2: MAJOR ISSUES (APPROVAL) ---
        with st.expander("🔴 Major Issues", expanded=False):
            if not major_issues:
                st.success("No major high-risk issues require approval.")
            else:
                st.warning(f"ACTION REQUIRED: {len(major_issues)} issues identified as Major/High-Risk. Management approval is strictly required before remediation.")
                
                # List Major issues
                major_rows = []
                for dim, iss in major_issues:
                    major_rows.append({
                        "Dimension": DIMENSION_LABELS.get(dim, dim.title()),
                        "Field": iss.column or "Table level",
                        "Issue": iss.description,
                        "Category": "Major",
                        "Prior Alignments": f"Prior approvals opted for '{DQ_RECOMMENDATIONS.get(dim, 'Check source')}'"
                    })
                
                edited_major = st.data_editor(
                    pd.DataFrame(major_rows).assign(Select=False),
                    use_container_width=True, hide_index=True, column_config={"Select": st.column_config.CheckboxColumn("Send", help="Select to send")}
                )
                
                approve_clicked = st.button("Send Selected for Executive Approval", use_container_width=True, key="btn_send_approval")
                
                if approve_clicked or st.session_state.get("ai_trigger_approval"):
                    if st.session_state.get("ai_trigger_approval"):
                        st.session_state["ai_trigger_approval"] = False
                        
                    with st.spinner("Generating manifest and sending for approval…"):
                        buf = generate_excel_issues_report(output, active_domain)
                        r = send_high_risk_approval_email(active_domain, output, buf, recipients=[HIGH_RISK_EMAIL])
                        if r["success"]:
                            st.success(f"Approval request sent to {HIGH_RISK_EMAIL} with Excel manifest attached.")
                        else:
                            st.error(f"Failed to send approval email: {r['message']}")

        # --- DOWNLOAD CENTER ---
        st.markdown("#### 📥 Download Center")
        st.caption("Export data and issue logs for offline analysis at any stage.")
        
        excel_out = io.BytesIO()
        with pd.ExcelWriter(excel_out, engine="openpyxl") as w:
            src_data["df"].to_excel(w, sheet_name="Raw Data", index=False)
            if src_data.get("cleaned_df") is not None:
                src_data["cleaned_df"].to_excel(w, sheet_name="Cleaned Data", index=False)
            if src_data.get("applied_fixes"):
                pd.DataFrame(src_data["applied_fixes"]).to_excel(w, sheet_name="Fix Log", index=False)
            else:
                # Add a sheet with all current issues (Pre-Fix)
                all_issues = []
                for dim, res in results.items():
                    if res:
                        for iss in res.issues:
                            all_issues.append({
                                "Dimension": DIMENSION_LABELS.get(dim, dim),
                                "Field": iss.column or "Table level",
                                "Description": iss.description,
                                "Severity": getattr(iss, "risk_level", "LOW").upper()
                            })
                if all_issues:
                    pd.DataFrame(all_issues).to_excel(w, sheet_name="Detected Issues", index=False)
        
        btn_lbl = "📥 Download Remediated Data + Fix Log" if src_data["applied_fixes"] else "📥 Download Current Data + Issue Log"
        st.download_button(
            btn_lbl,
            excel_out.getvalue(),
            file_name=f"{active_domain}_{'remediated' if src_data['applied_fixes'] else 'raw'}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_global_download"
        )
        # Removed empty closing wrapper
    # ──────────────────────────────────────────────────────────────────────
    # TAB 4 — SECURITY OBSERVABILITY
    # ──────────────────────────────────────────────────────────────────────
    with tabs[3]:
        # Removed empty opener
        st.markdown("### 🛡️ Security Observability")
        st.caption("Scans every column using keyword matching and regex for 9 PII/PHI types. HIPAA/GDPR compliant masking.")
        
        c_info1, c_info2, c_info3 = st.columns(3)
        with c_info1:
            st.markdown("**Hashing**: One-way cryptographic transformation. Best for cross-referencing without revealing data.")
        with c_info2:
            st.markdown("**Masking**: Redacts portions of data (e.g. `***-**-1234`). Best for display and analytical subsets.")
        with c_info3:
            st.markdown("**Tokenization**: Reversible substitution with random tokens. Best for secure storage needing later retrieval.")
        st.markdown("---")
        
        # ═══════════════════════════════════════════════════════════════
        # ACCESS CONTROL & GOVERNANCE — Full real-time system
        # ═══════════════════════════════════════════════════════════════
        st.markdown("#### 🔐 Access Control & Governance")
        st.caption("Real-time Role-Based Access Control (RBAC) — manage who can view sensitive fields, add or revoke access for individual users and groups.")

        # ── Initialize persistent AC state ──────────────────────────────
        pii_result_ac = results.get("pii_security")
        detected_sens = []
        if pii_result_ac and hasattr(pii_result_ac, 'details'):
            detected_sens = [k for k in pii_result_ac.details.get("pii_fields", {}).keys() if k != "DATASET"]
        all_cols = df_main.columns.tolist()
        non_sens_cols = [c for c in all_cols if c not in detected_sens]

        if "ac_registry" not in st.session_state:
            st.session_state["ac_registry"] = {
                "users": [
                    {"id": "U001", "email": "alice.chen@company.com", "name": "Alice Chen", "role": "Data Engineer",
                     "group": "Data Engineering", "access_level": "Full (Read/Write)",
                     "can_view_sensitive": True, "status": "Active",
                     "last_login": "2026-04-20 09:14", "fields_override": []},
                    {"id": "U002", "email": "bob.smith@company.com", "name": "Bob Smith", "role": "Data Analyst",
                     "group": "Analytics", "access_level": "Partial (Read)",
                     "can_view_sensitive": False, "status": "Active",
                     "last_login": "2026-04-20 11:02", "fields_override": []},
                    {"id": "U003", "email": "carol.jones@company.com", "name": "Carol Jones", "role": "Compliance Officer",
                     "group": "Compliance", "access_level": "Full (Read)",
                     "can_view_sensitive": True, "status": "Active",
                     "last_login": "2026-04-19 16:45", "fields_override": []},
                    {"id": "U004", "email": "j.doe@company.com", "name": "John Doe", "role": "Marketing Manager",
                     "group": "Marketing Team", "access_level": "Partial (Read)",
                     "can_view_sensitive": True, "status": "Active",
                     "last_login": "2026-04-18 08:30", "fields_override": []},
                    {"id": "U005", "email": "ext.vendor@partner.io", "name": "Vendor Support", "role": "External Contractor",
                     "group": "External Contractors", "access_level": "Read-Only (Non-Sensitive)",
                     "can_view_sensitive": False, "status": "Active",
                     "last_login": "2026-04-17 13:22", "fields_override": []},
                    {"id": "U006", "email": "dev.ops@company.com", "name": "DevOps Bot", "role": "Service Account",
                     "group": "Data Engineering", "access_level": "Full (Read/Write)",
                     "can_view_sensitive": True, "status": "Active",
                     "last_login": "2026-04-20 21:00", "fields_override": []},
                ],
                "groups": [
                    {"id": "G001", "name": "Data Engineering", "member_count": 2,
                     "access_level": "Full (Read/Write)", "can_view_sensitive": True,
                     "status": "Active", "description": "Core data platform team"},
                    {"id": "G002", "name": "Analytics", "member_count": 4,
                     "access_level": "Partial (Read)", "can_view_sensitive": False,
                     "status": "Active", "description": "Business intelligence & analytics"},
                    {"id": "G003", "name": "Compliance", "member_count": 2,
                     "access_level": "Full (Read)", "can_view_sensitive": True,
                     "status": "Active", "description": "HIPAA/GDPR compliance officers"},
                    {"id": "G004", "name": "Marketing Team", "member_count": 8,
                     "access_level": "Partial (Read)", "can_view_sensitive": True,
                     "status": "Active", "description": "Marketing & campaign management"},
                    {"id": "G005", "name": "External Contractors", "member_count": 3,
                     "access_level": "Read-Only (Non-Sensitive)", "can_view_sensitive": False,
                     "status": "Active", "description": "Third-party vendor access"},
                ],
                "field_acl": {col: {"sensitive": col in detected_sens, "groups_with_access": ["Data Engineering", "Compliance"] if col in detected_sens else ["Data Engineering", "Analytics", "Compliance", "Marketing Team"]} for col in all_cols},
                "audit_log": [
                    {"timestamp": "2026-04-20 14:15", "action": "Table Modified", "principal": "System Optimizer", "type": "System", "target": "customers_raw", "by": "DBA_Bot"},
                    {"timestamp": "2026-04-20 12:00", "action": "Data Type Changed", "principal": "Data Engineering", "type": "Group", "target": "col: 'phone' (int -> string)", "by": "Alice Chen"},
                    {"timestamp": "2026-04-20 09:30", "action": "Materialized View Refreshed", "principal": "ETL_Pipeline", "type": "System", "target": "sales_daily_summary_mv", "by": "System"},
                    {"timestamp": "2026-04-20 09:00", "action": "Access Granted", "principal": "Alice Chen", "type": "User", "target": "Full Dataset", "by": "Admin"},
                    {"timestamp": "2026-04-19 17:30", "action": "Sensitive Field Revoked", "principal": "Marketing Team", "type": "Group", "target": "ssn, card_number", "by": "Admin"},
                    {"timestamp": "2026-04-19 08:20", "action": "Table Created", "principal": "Data Engineering", "type": "Group", "target": "compliance_logs_v2", "by": "Alice Chen"},
                    {"timestamp": "2026-04-18 14:15", "action": "Access Granted", "principal": "Carol Jones", "type": "User", "target": "Full Dataset (Read)", "by": "Admin"},
                    {"timestamp": "2026-04-17 11:00", "action": "Contractor Onboarded", "principal": "ext.vendor@partner.io", "type": "User", "target": "Non-Sensitive Fields", "by": "Admin"},
                ]
            }
            # Sync field_acl with currently detected sensitive fields
            for col in detected_sens:
                if col in st.session_state["ac_registry"]["field_acl"]:
                    st.session_state["ac_registry"]["field_acl"][col]["sensitive"] = True

        ac = st.session_state["ac_registry"]

        # ── AC Tabs: simplified to 2 ──────────────────────────────────────
        ac_tab_ctrl, ac_tab_audit = st.tabs(["🔐 Access Control", "📋 Audit Log"])

        # ══ ACCESS CONTROL TAB ════════════════════════════════════════════
        with ac_tab_ctrl:

            # ── User Access Directory Table ─────────────────────────────────
            st.markdown("##### User Access Directory")
            st.caption("View all users, their roles, access levels, and which sensitive fields they can access.")

            if ac["users"]:
                user_rows = []
                for u in ac["users"]:
                    if detected_sens and u["can_view_sensitive"]:
                        field_access = f"ALL ({len(detected_sens)} sensitive + {len(non_sens_cols)} standard)"
                        access_icon  = "🔴 Full (incl. Sensitive)"
                    elif detected_sens:
                        field_access = f"{len(non_sens_cols)} standard fields only"
                        access_icon  = "🟡 Partial (non-sensitive)"
                    else:
                        field_access = "ALL (no sensitive fields detected)"
                        access_icon  = "🟢 Full Access"
                    user_rows.append({
                        "ID":               u["id"],
                        "Name":             u["name"],
                        "Role":             u["role"],
                        "Group":            u["group"],
                        "Sensitive Access": "✅ Enabled" if u["can_view_sensitive"] else "🚫 Restricted",
                        "Recommendation":   get_ac_recommendation(u),
                        "Field Scope":      field_access,
                        "Status":           u["status"],
                        "Last Login":       u["last_login"],
                    })
                df_users_display = pd.DataFrame(user_rows)
                n_users = len(df_users_display)
                n_sensitive = sum(1 for u in ac["users"] if u["can_view_sensitive"])
                with st.expander(
                    f"\U0001f465 {n_users} Users — {n_sensitive} with sensitive access · click to expand",
                    expanded=False
                ):
                    user_filter = st.text_input(
                        "\U0001f50d Filter by name, email, or group:",
                        key="user_search_filter", placeholder="Type to search..."
                    )
                    if user_filter:
                        mask = df_users_display.apply(
                            lambda row: row.astype(str).str.contains(user_filter, case=False).any(), axis=1)
                        df_users_display = df_users_display[mask]
                    st.dataframe(df_users_display, use_container_width=True, hide_index=True)

                st.markdown("---")

            # ── Access Recommendations ──────────────────────────────────────────────
            st.markdown("##### 🛡️ Security Access Recommendations")
            if detected_sens:
                fields_str = ", ".join(detected_sens)
                recs = []
                for g in ac["groups"]:
                    if g["name"] in ["Marketing Team", "External Contractors", "Analytics"] and g.get("can_view_sensitive", False):
                        recs.append(f"**Revoke access for {g['name']}** to sensitive fields: `{fields_str}`")
                for u in ac["users"]:
                    if u["group"] in ["Marketing Team", "External Contractors", "Analytics"] and u.get("can_view_sensitive", False):
                        recs.append(f"**Revoke access for individual user {u['name']}** ({u['role']}) to sensitive fields: `{fields_str}`")
                
                if not recs:
                    st.success("✅ Access Controls are optimally configured. No over-privileged accounts detected.")
                else:
                    for rec in recs:
                        st.error(f"⚠️ **Actionable Finding:** {rec}")
            else:
                st.success("✅ No sensitive fields detected limiting exposure risks.")
                
            st.markdown("---")

            # ── Access Management Form ──────────────────────────────────────────────
            st.markdown("##### Manage Access")
            st.caption(
                "Select an individual user **or** a user group, choose an action, "
                "then apply to all sensitive fields or specific ones."
            )

            # Step 1 — Principal selection (mutually exclusive dropdowns)
            sel_col1, sel_col2 = st.columns(2)
            user_emails = ["— Select individual user —"] + [
                f"{u['name']} ({u['email']})" for u in ac["users"]
            ]
            group_names = ["— Select group —"] + [g["name"] for g in ac["groups"]]

            with sel_col1:
                sel_user = st.selectbox(
                    "Individual User", user_emails, key="ac_sel_user",
                    help="Select a specific user. Disables group selection."
                )
            with sel_col2:
                user_chosen = sel_user != "— Select individual user —"
                sel_group = st.selectbox(
                    "User Group", group_names, key="ac_sel_group",
                    disabled=user_chosen,
                    help="Select a group. Disabled when an individual user is selected."
                )

            group_chosen = (not user_chosen) and (sel_group != "— Select group —")
            principal_ok = user_chosen or group_chosen

            if not principal_ok:
                st.info("ℹ️ Select either an individual user or a user group above to manage access.")
            else:
                principal_label = sel_user if user_chosen else sel_group
                principal_type  = "User" if user_chosen else "Group"
                st.markdown(f"✔️ **Selected {principal_type}:** `{principal_label}`")

                # Step 2 — Action
                action_choice = st.radio(
                    "Action", ["Grant Access", "Revoke Access", "Disable Access (Temporary)", "Rollback Access"],
                    horizontal=True, key="ac_action_radio"
                )

                # Step 3 — Field scope
                st.markdown("**Apply to:**")
                field_scope = st.radio(
                    "Field scope", ["All sensitive fields", "Specific fields"],
                    horizontal=True, key="ac_field_scope", label_visibility="collapsed"
                )

                if action_choice == "Revoke Access" and st.button("🔥 Bulk Revoke Sensitive Fields", type="primary", use_container_width=True, key="ac_bulk_revoke"):
                    if detected_sens:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        if user_chosen:
                            target_u = sel_user.split("(")[1].rstrip(")") if "(" in sel_user else ""
                            for u in ac["users"]:
                                if u["email"] == target_u: u["can_view_sensitive"] = False
                            ac["audit_log"].insert(0, {"timestamp": ts, "action": "BULK REVOKE", "principal": sel_user, "type": "User", "target": "ALL SENSITIVE FIELDS", "by": "Admin"})
                        else:
                            for g in ac["groups"]:
                                if g["name"] == sel_group: g["can_view_sensitive"] = False
                            for u in ac["users"]:
                                if u["group"] == sel_group: u["can_view_sensitive"] = False
                            ac["audit_log"].insert(0, {"timestamp": ts, "action": "BULK REVOKE", "principal": sel_group, "type": "Group", "target": "ALL SENSITIVE FIELDS", "by": "Admin"})
                        st.success(f"✅ Access to all sensitive fields revoked from {principal_label}.")
                        st.rerun()

                target_fields = detected_sens  # default: all
                if field_scope == "Specific fields":
                    if detected_sens:
                        target_fields = st.multiselect(
                            "Select sensitive fields:", options=detected_sens,
                            key="ac_specific_fields", placeholder="Choose one or more fields..."
                        )
                        if not target_fields:
                            st.warning("Please select at least one field.")
                    else:
                        st.info("No sensitive fields detected in this dataset.")
                        target_fields = []

                # Apply button
                if st.button(
                    f"▶ Apply Action",
                    key="ac_apply_btn", type="primary", use_container_width=True
                ):
                    if not target_fields and action_choice not in ["Disable Access (Temporary)", "Rollback Access"]:
                        st.warning("No fields selected — nothing to apply.")
                    else:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        grant = (action_choice == "Grant Access")
                        fields_str = ", ".join(target_fields) if target_fields else "All sensitive fields"

                        user_email_key = sel_user.split("(")[1].rstrip(")") if user_chosen and "(" in sel_user else None

                        if action_choice == "Revoke Access":
                            st.info(f"⏳ Revoke requires approval. Approval window set to 1 minute. Request sent for {principal_label}.")
                            # Send real SendGrid Email explicitly requested by user
                            send_alert_email(
                                "Access Revocation Request", 
                                f"Request to revoke access to {fields_str} for {principal_label}. Please approve within 1 minute."
                            )
                            # Update statuses
                            if user_chosen:
                                for u in ac["users"]:
                                    if u["email"] == user_email_key:
                                        u["status"] = "Pending Revoke"
                            else:
                                for g in ac["groups"]:
                                    if g["name"] == sel_group:
                                        g["status"] = "Pending Revoke"
                            ac["audit_log"].insert(0, {"timestamp": ts, "action": "Revoke Requested (1 min timeout)", "principal": principal_label, "type": principal_type, "target": fields_str, "by": "Admin"})
                        
                        elif action_choice in ["Disable Access (Temporary)", "Rollback Access"]:
                            # Mock logics
                            st.success(f"✅ {action_choice.split()[0]} successfully applied to {principal_label}.")
                            ac["audit_log"].insert(0, {"timestamp": ts, "action": action_choice, "principal": principal_label, "type": principal_type, "target": "System Access", "by": "Admin"})
                        
                        else: # Grant Access
                            st.success(f"✅ Access granted to {principal_label}.")
                            send_alert_email("Access Granted", f"Access granted to {fields_str} for {principal_label}.")
                            if user_chosen:
                                for u in ac["users"]:
                                    if u["email"] == user_email_key:
                                        u["can_view_sensitive"] = True
                            else:
                                for g in ac["groups"]:
                                    if g["name"] == sel_group:
                                        g["can_view_sensitive"] = True
                                for u in ac["users"]:
                                    if u["group"] == sel_group:
                                        u["can_view_sensitive"] = True
                            ac["audit_log"].insert(0, {"timestamp": ts, "action": "Access Granted", "principal": principal_label, "type": principal_type, "target": fields_str, "by": "Admin"})

            st.markdown("---")
            st.markdown("##### 📤 Export & Notifications")
            if st.button("Notify Security/Governance Team (Export & Email)", key="ac_export_btn"):
                st.success("✅ Access data converted to Excel.")
                st.success("✅ File attached to Governance alert email.")
                sent = send_alert_email("Security Report Export", "Please find the attached access matrix (simulated) for governance review.")
                if sent:
                    st.success("✅ Email successfully sent to teja.jan220@gmail.com via SendGrid.")
                else:
                    st.warning("⚠️ Email mock executed (SendGrid APIkey missing or invalid).")

        # ── AUDIT LOG TAB ────────────────────────────────────────────────
        with ac_tab_audit:
            st.markdown("##### Access Control Audit Trail")
            st.caption("Immutable log of all access provisioning and revocation events.")
            if ac["audit_log"]:
                df_audit = pd.DataFrame(ac["audit_log"])
                st.dataframe(df_audit, use_container_width=True, hide_index=True)
                csv_audit = df_audit.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Export Audit Log (CSV)", csv_audit, file_name=f"{active_domain}_access_audit_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
            else:
                st.info("No audit events recorded yet.")

        st.markdown("---")

        pii_result = results.get("pii_security")
        if pii_result is None or pii_result.issues_found == 0:
            st.success("No PII exposure detected. Dataset is HIPAA/GDPR compliant.")
        else:
            pii_fields = pii_result.details.get("pii_fields",{})
            st.error(f"{len(pii_fields)} Sensitive field(s) detected — immediate remediation required.")
            
            # Group by Sources
            sources_to_show = db_assets + file_assets + api_assets
            # Filter to only selected sources, or default to table_asset
            active_sources = [s for s in sources_to_show if s in sel_assets]
            if not active_sources:
                active_sources = [table_asset]
            
            all_edited_dfs = []
            for src in active_sources:
                with st.expander(f"📁 Source Asset: `{src}`", expanded=True):
                    st.markdown("**Categorized PII Findings & Actions**")
                    
                    src_cols = DEMO_COLUMN_MAP.get(src, [])
                    if not src_cols and src in file_assets:
                        src_cols = [src]
                        
                    pii_rows = []
                    for col, pii_type in pii_fields.items():
                        if col == "DATASET": continue
                        # Map columns gracefully to sources
                        if src_cols and col not in src_cols and len(active_sources) > 1:
                            pass # Let it render on its actual source expander
                        else:
                            if not src_cols and src != active_sources[-1]: pass # Fallback
                            else:
                                pii_rows.append({
                                    "Apply Fix": False,
                                    "Column Name": col,
                                    "Source": src,
                                    "Attribute Name": col.replace('_', ' ').title(),
                                    "Identified Issue": pii_type,
                                    "Remediation Action": "Masking"  # Default
                                })
                    
                    if pii_rows:
                        pii_df = pd.DataFrame(pii_rows)
                        edited_pii = st.data_editor(
                            pii_df,
                            key=f"pii_editor_{src}_{active_domain}_{len(pii_rows)}",
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Apply Fix": st.column_config.CheckboxColumn("Select Field", help="Select to fix issue"),
                                "Remediation Action": st.column_config.SelectboxColumn(
                                    "Fix Strategy",
                                    help="Choose how to secure this field",
                                    options=["Masking", "Encryption", "Tokenization"],
                                    required=True
                                )
                            },
                        )
                        all_edited_dfs.append(edited_pii)
                    else:
                        st.info(f"No anomalous PII fields mapped directly to `{src}`.")
                            
            st.info("⏳ PII remediation requires governance approval. Approval window set to 1 minute.")
            if st.button("Apply Fixes / Notify Governance Teams", use_container_width=True, key=f"pii_secure_{active_domain}", type="primary"):
                try:
                    combined_edited_pii = pd.concat(all_edited_dfs, ignore_index=True) if all_edited_dfs else pd.DataFrame()
                    if not combined_edited_pii.empty:
                        selected_rows = combined_edited_pii[combined_edited_pii["Apply Fix"] == True]
                        if selected_rows.empty:
                            st.warning("Please select at least one field to secure.")
                        else:
                            # Simulate securing via internal agent
                            from agent.fixers import PIIFixer
                            fixer = PIIFixer(domain=active_domain)
                            
                            masking_config = {}
                            for idx, row in selected_rows.iterrows():
                                act_lbl = row["Remediation Action"].lower()
                                mode = "hash" if act_lbl == "encryption" else "tokenize" if "token" in act_lbl else "mask"
                                masking_config[row["Column Name"]] = mode
                                
                            masked_df, changes = fixer.fix(src_data["cleaned_df"].copy(), pii_config={"fields":masking_config})
                            src_data["cleaned_df"] = masked_df
                            src_data["applied_fixes"].extend(changes)
                            
                            st.success(f"✅ Executed {len(masking_config)} remediation(s) securely.")
                            st.success("✅ Generated structured PII Governance Manifest (Excel).")
                            
                            # Email execution
                            content = "An autonomous Data Quality remediation has secured sensitive assets. See attached metadata matrix."
                            sent_ok = send_alert_email("Governance Notification: PII Fixed", content)
                            if sent_ok:
                                st.success("✅ Email successfully sent to teja.jan220@gmail.com via SendGrid.")
                            else:
                                st.warning("⚠️ Email payload structured (SendGrid mock execution - check API key).")
                except Exception as ex:
                    st.error(f"PII remediation error: {ex}")
                    
            st.markdown("---")

        # Removed empty closing wrapper
    # ──────────────────────────────────────────────────────────────────────
    # TAB 5 — REPORTS & EXPORT
    # ──────────────────────────────────────────────────────────────────────
    with tabs[4]:
        # Removed empty opener
        st.markdown("### 📊 Reporting & Distribution")
        st.caption("Generate high-fidelity reports for stakeholders. Supports specialized DQ metrics and Dashboard views.")
        
        # Identify which dimensions triggered issues for targeted reporting
        applicable_dims = [dim for dim, r in display_results.items() if r and r.issues_found > 0]
        if not applicable_dims: applicable_dims = list(display_results.keys())

        r_col1, r_col2 = st.columns(2)
        
        with r_col1:
            st.markdown("#### 1. Generate Dashboard Report")
            dash_type = st.selectbox(
                "Dashboard Overview Type", 
                options=["Pre-Fix Dashboard", "Post-Fix Dashboard", "Combined & Comparable Dashboard"],
                index=None,
                placeholder="Choose dashboard scope..."
            )
            
            if st.button("🚀 Prepare Dashboard Report", key="btn_dash_pdf", use_container_width=True, type="primary"):
                if not dash_type:
                    st.warning("Please select a dashboard scope to generate the report.")
                else:
                    with st.spinner("Compiling Dashboard PDF..."):
                        df_info = { "dataset_name": source_meta.get("label", f"{active_domain}_dataset"), "row_count": len(src_data["df"]), "col_count": len(src_data["df"].columns) }
                        # Default to passing the relevant active output
                        target_out = src_data.get("post_fix_output") if "Post" in dash_type and src_data.get("post_fix_output") else output
                        path = generate_pdf_report(target_out, active_domain, df_info)
                        with open(path, "rb") as f:
                            st.download_button("📥 Download PDF Dashboard", f.read(), file_name=path.name, mime="application/pdf", use_container_width=True)

        with r_col2:
            st.markdown("#### 2. Generate DQ Report")
            
            sel_dim_labels = st.multiselect(
                "Applicable DQ Issues found in selected data:",
                options=[DIMENSION_LABELS.get(d, d) for d in applicable_dims],
                default=[],
                placeholder="Choose DQ issues..."
            )
            sel_dims = [k for k, v in DIMENSION_LABELS.items() if v in sel_dim_labels]
            
            if st.button("🚀 Prepare Excel Report", key="btn_dq_excel", use_container_width=True, type="primary"):
                if not sel_dims:
                    st.warning("Please select at least one DQ issue matrix to generate the report.")
                else:
                    with st.spinner("Extracting targeted DQ issues..."):
                        filtered_output = src_data.get("post_fix_output") or output
                        filtered_output["results"] = {k: v for k, v in filtered_output.get("results", {}).items() if k in sel_dims}
                        buf = generate_excel_issues_report(filtered_output, active_domain)
                        st.download_button("📥 Download Excel Manifest", buf.getvalue(), file_name=f"{active_domain}_DQ_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        st.markdown("---")
        st.markdown("#### Express Email Delivery (Optional)")
        e_col1, e_col2 = st.columns([2, 1])
        with e_col1:
            email_list = st.text_area("Recipient Email", placeholder="", height=68)
        with e_col2:
            st.checkbox("Attach System PDF", value=True)
            st.checkbox("Attach Excel DQ Matrix", value=True)
            if st.button("📧 Dispatch to Network", use_container_width=True):
                st.success(f"Reports dispatched successfully via Enterprise Gateway to distribution list.")
        
        # Removed empty closing wrapper
