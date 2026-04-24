"""
DQ Agent Framework — SQLite Database Layer
Manages persistence for: issue logs, fix history, learning engine, business rules.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
import numpy as np

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

DB_PATH = Path(__file__).parent / "dq_metadata.db"

def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize all database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        -- ── Analysis Runs ──────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_name TEXT    NOT NULL,
            domain       TEXT    NOT NULL,
            row_count    INTEGER NOT NULL,
            col_count    INTEGER NOT NULL,
            overall_score REAL   NOT NULL,
            run_timestamp TEXT   NOT NULL,
            run_duration_sec REAL,
            summary_json TEXT
        );

        -- ── Dimension Scores ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS dimension_scores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES analysis_runs(run_id),
            dimension   TEXT    NOT NULL,
            score       REAL    NOT NULL,
            issues_found INTEGER NOT NULL DEFAULT 0,
            severity    TEXT    NOT NULL DEFAULT 'LOW',
            details_json TEXT
        );

        -- ── Issue Log ───────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS issue_log (
            issue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES analysis_runs(run_id),
            domain      TEXT    NOT NULL,
            dimension   TEXT    NOT NULL,
            column_name TEXT,
            issue_type  TEXT    NOT NULL,
            description TEXT    NOT NULL,
            affected_rows INTEGER DEFAULT 0,
            affected_pct  REAL   DEFAULT 0.0,
            severity    TEXT    NOT NULL DEFAULT 'LOW',
            risk_level  TEXT    NOT NULL DEFAULT 'LOW',
            sample_values TEXT,
            row_indices TEXT,
            logged_at   TEXT    NOT NULL
        );

        -- ── Fix History ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS fix_history (
            fix_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id     INTEGER REFERENCES issue_log(issue_id),
            run_id       INTEGER REFERENCES analysis_runs(run_id),
            domain       TEXT    NOT NULL,
            dimension    TEXT    NOT NULL,
            column_name  TEXT,
            fix_action   TEXT    NOT NULL,
            fix_params   TEXT,
            rows_affected INTEGER DEFAULT 0,
            status       TEXT    NOT NULL DEFAULT 'Applied',
            applied_by   TEXT    DEFAULT 'user',
            applied_at   TEXT    NOT NULL,
            notes        TEXT
        );

        -- ── Learning Engine ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS learning_patterns (
            pattern_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            domain       TEXT    NOT NULL,
            dimension    TEXT    NOT NULL,
            column_name  TEXT,
            issue_type   TEXT    NOT NULL,
            fix_action   TEXT    NOT NULL,
            occurrence_count INTEGER DEFAULT 1,
            success_count    INTEGER DEFAULT 0,
            failure_count    INTEGER DEFAULT 0,
            success_rate     REAL    DEFAULT 0.0,
            last_seen        TEXT    NOT NULL,
            auto_fix_eligible INTEGER DEFAULT 0
        );

        -- ── Business Rules (dynamic) ────────────────────────────────
        CREATE TABLE IF NOT EXISTS custom_business_rules (
            rule_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            domain       TEXT    NOT NULL,
            rule_name    TEXT    NOT NULL,
            description  TEXT,
            rule_type    TEXT    NOT NULL DEFAULT 'field',
            target_field TEXT,
            rule_expression TEXT NOT NULL,
            severity     TEXT    NOT NULL DEFAULT 'MEDIUM',
            fix_action   TEXT,
            is_active    INTEGER DEFAULT 1,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL
        );

        -- ── PII Masking Log ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS pii_masking_log (
            mask_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER REFERENCES analysis_runs(run_id),
            domain       TEXT    NOT NULL,
            pii_field    TEXT    NOT NULL,
            masking_mode TEXT    NOT NULL,
            rows_masked  INTEGER DEFAULT 0,
            masked_at    TEXT    NOT NULL
        );

        -- ── Audit Trail ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS audit_trail (
            audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type   TEXT    NOT NULL,
            event_detail TEXT,
            domain       TEXT,
            user_action  TEXT,
            timestamp    TEXT    NOT NULL
        );
    """)

    conn.commit()
    conn.close()


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def log_analysis_run(dataset_name: str, domain: str, row_count: int, col_count: int,
                     overall_score: float, duration_sec: float, summary: dict) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO analysis_runs
           (dataset_name, domain, row_count, col_count, overall_score,
            run_timestamp, run_duration_sec, summary_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (dataset_name, domain, row_count, col_count, round(overall_score, 2),
         datetime.now().isoformat(), round(duration_sec, 3), json.dumps(summary, cls=NpEncoder))
    )
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_dimension_score(run_id: int, dimension: str, score: float,
                        issues_found: int, severity: str, details: dict):
    conn = get_connection()
    conn.execute(
        """INSERT INTO dimension_scores
           (run_id, dimension, score, issues_found, severity, details_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (run_id, dimension, round(score, 2), issues_found, severity, json.dumps(details, cls=NpEncoder))
    )
    conn.commit()
    conn.close()


def log_issue(run_id: int, domain: str, dimension: str, column_name: str,
              issue_type: str, description: str, affected_rows: int,
              affected_pct: float, severity: str, risk_level: str,
              sample_values=None, row_indices=None) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO issue_log
           (run_id, domain, dimension, column_name, issue_type, description,
            affected_rows, affected_pct, severity, risk_level,
            sample_values, row_indices, logged_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, domain, dimension, column_name, issue_type, description,
         affected_rows, round(affected_pct, 4), severity, risk_level,
         json.dumps(sample_values, cls=NpEncoder) if sample_values else None,
         json.dumps(row_indices[:100], cls=NpEncoder) if row_indices else None,
         datetime.now().isoformat())
    )
    issue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return issue_id


def log_fix(run_id: int, issue_id: int, domain: str, dimension: str,
            column_name: str, fix_action: str, rows_affected: int,
            fix_params: dict = None, notes: str = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO fix_history
           (issue_id, run_id, domain, dimension, column_name, fix_action,
            fix_params, rows_affected, status, applied_at, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Applied', ?, ?)""",
        (issue_id, run_id, domain, dimension, column_name, fix_action,
         json.dumps(fix_params, cls=NpEncoder) if fix_params else None,
         rows_affected, datetime.now().isoformat(), notes)
    )
    conn.commit()
    conn.close()


def update_learning_pattern(domain: str, dimension: str, column_name: str,
                            issue_type: str, fix_action: str, success: bool):
    conn = get_connection()
    existing = conn.execute(
        """SELECT pattern_id, occurrence_count, success_count, failure_count
           FROM learning_patterns
           WHERE domain=? AND dimension=? AND column_name=? AND issue_type=? AND fix_action=?""",
        (domain, dimension, column_name, issue_type, fix_action)
    ).fetchone()

    if existing:
        sc = existing["success_count"] + (1 if success else 0)
        fc = existing["failure_count"] + (0 if success else 1)
        oc = existing["occurrence_count"] + 1
        sr = sc / oc
        auto_eligible = 1 if (oc >= 3 and sr >= 0.95) else 0
        conn.execute(
            """UPDATE learning_patterns
               SET occurrence_count=?, success_count=?, failure_count=?,
                   success_rate=?, last_seen=?, auto_fix_eligible=?
               WHERE pattern_id=?""",
            (oc, sc, fc, round(sr, 4), datetime.now().isoformat(),
             auto_eligible, existing["pattern_id"])
        )
    else:
        sc = 1 if success else 0
        conn.execute(
            """INSERT INTO learning_patterns
               (domain, dimension, column_name, issue_type, fix_action,
                occurrence_count, success_count, failure_count, success_rate,
                last_seen, auto_fix_eligible)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 0)""",
            (domain, dimension, column_name, issue_type, fix_action,
             sc, 0 if success else 1, 1.0 if success else 0.0,
             datetime.now().isoformat())
        )

    conn.commit()
    conn.close()


def get_learning_recommendation(domain: str, dimension: str, column_name: str,
                                issue_type: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT fix_action, occurrence_count, success_rate, auto_fix_eligible
           FROM learning_patterns
           WHERE domain=? AND dimension=? AND column_name=? AND issue_type=?
           ORDER BY success_rate DESC, occurrence_count DESC
           LIMIT 1""",
        (domain, dimension, column_name, issue_type)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_recent_runs(domain: str = None, limit: int = 20) -> list:
    conn = get_connection()
    if domain:
        rows = conn.execute(
            "SELECT * FROM analysis_runs WHERE domain=? ORDER BY run_id DESC LIMIT ?",
            (domain, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM analysis_runs ORDER BY run_id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_issue_log(run_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM issue_log WHERE run_id=? ORDER BY severity DESC, affected_rows DESC",
        (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_fix_history(domain: str = None, limit: int = 100) -> list:
    conn = get_connection()
    if domain:
        rows = conn.execute(
            "SELECT * FROM fix_history WHERE domain=? ORDER BY fix_id DESC LIMIT ?",
            (domain, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fix_history ORDER BY fix_id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_learning_patterns() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM learning_patterns ORDER BY occurrence_count DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_custom_rule(domain: str, rule_name: str, description: str,
                     rule_type: str, target_field: str, rule_expression: str,
                     severity: str, fix_action: str) -> int:
    conn = get_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """INSERT INTO custom_business_rules
           (domain, rule_name, description, rule_type, target_field,
            rule_expression, severity, fix_action, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (domain, rule_name, description, rule_type, target_field,
         rule_expression, severity, fix_action, now, now)
    )
    rule_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return rule_id


def get_custom_rules(domain: str = None) -> list:
    conn = get_connection()
    if domain:
        rows = conn.execute(
            "SELECT * FROM custom_business_rules WHERE domain=? AND is_active=1",
            (domain,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM custom_business_rules WHERE is_active=1"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_audit_event(event_type: str, detail: str, domain: str = None, user_action: str = None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_trail (event_type, event_detail, domain, user_action, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (event_type, detail, domain, user_action, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_column_history(domain: str, column_name: str) -> dict:
    conn = get_connection()
    issues = conn.execute(
        "SELECT * FROM issue_log WHERE domain=? AND column_name=? ORDER BY logged_at DESC",
        (domain, column_name)
    ).fetchall()
    
    fixes = conn.execute(
        "SELECT * FROM fix_history WHERE domain=? AND column_name=? ORDER BY applied_at DESC",
        (domain, column_name)
    ).fetchall()
    conn.close()
    
    return {
        "issues": [dict(r) for r in issues],
        "fixes": [dict(r) for r in fixes]
    }


def get_global_summary() -> dict:
    """Return aggregate DQ stats across all domains from the latest run per domain."""
    conn = get_connection()
    # Get latest run_id per domain
    latest_runs = conn.execute(
        "SELECT domain, MAX(run_id) as latest_run_id, overall_score, row_count FROM analysis_runs GROUP BY domain"
    ).fetchall()

    result = {}
    for run in latest_runs:
        domain = run["domain"]
        run_id = run["latest_run_id"]
        dim_scores = conn.execute(
            "SELECT dimension, score FROM dimension_scores WHERE run_id=?", (run_id,)
        ).fetchall()
        issue_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM issue_log WHERE run_id=?", (run_id,)
        ).fetchone()
        result[domain] = {
            "overall_score": run["overall_score"],
            "row_count": run["row_count"],
            "total_issues": issue_count["cnt"] if issue_count else 0,
            "dimensions": {d["dimension"]: d["score"] for d in dim_scores},
            "run_id": run_id,
        }
    conn.close()
    return result


# Initialize on import
init_db()
