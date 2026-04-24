"""
Data Source Connectors — plug-and-play ingestion layer.

Three real connectors that each return (pd.DataFrame, source_meta dict):
  • DatabaseConnector — SQLAlchemy-backed: PostgreSQL, MySQL, MSSQL, SQLite, Snowflake
  • FlatFileConnector  — pandas-backed: CSV, Parquet, JSON, Excel (local path or HTTP URL)
  • APIConnector       — requests-backed: any JSON REST API with optional dot-path normalisation

All three pipe into DQAgent.load_data(df), which runs all 23 DQ dimensions.

Error handling
--------------
Every connector raises a descriptive Exception on failure.
The caller (app.py) catches it and falls back to the demo CSV with a warning banner.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# DATABASE CONNECTOR
# ──────────────────────────────────────────────────────────────────────────────

class DatabaseConnector:
    """
    Connect to any SQLAlchemy-compatible relational database and pull a table
    (or the result of a custom SQL query) into a pandas DataFrame.

    Supported db_type values
    ------------------------
    postgresql  → needs: psycopg2        (pip install psycopg2-binary)
    mysql       → needs: pymysql         (pip install pymysql)
    mssql       → needs: pymssql         (pip install pymssql)
    sqlite      → built-in (host = full file path)
    snowflake   → needs: snowflake-sqlalchemy + snowflake-connector-python
    """

    _DRIVERS = {
        "postgresql": "postgresql+psycopg2",
        "postgres":   "postgresql+psycopg2",
        "mysql":      "mysql+pymysql",
        "mssql":      "mssql+pymssql",
        "sqlserver":  "mssql+pymssql",
        "sqlite":     "sqlite",
        "snowflake":  "snowflake",
    }

    # ── connection URL builders ─────────────────────────────────────────────

    def _build_url(
        self,
        db_type: str,
        host: str,
        port: int,
        dbname: str,
        username: str,
        password: str,
        snowflake_account: str = "",
        snowflake_warehouse: str = "",
        snowflake_schema: str = "PUBLIC",
    ) -> str:
        driver = self._DRIVERS.get(db_type.lower(), "postgresql+psycopg2")
        if db_type.lower() == "sqlite":
            # host = full file path for SQLite
            return f"sqlite:///{host}"
        if db_type.lower() == "snowflake":
            acct = snowflake_account or host
            return (
                f"snowflake://{username}:{password}@{acct}/"
                f"{dbname}/{snowflake_schema}?warehouse={snowflake_warehouse}"
            )
        return f"{driver}://{username}:{password}@{host}:{port}/{dbname}"

    def _mask_url(self, url: str, password: str) -> str:
        if password:
            return url.replace(password, "***")
        return url

    # ── table discovery ────────────────────────────────────────────────────

    def get_tables(self, engine) -> list[str]:
        try:
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(engine)
            return inspector.get_table_names()
        except Exception:
            return []

    # ── main entry point ───────────────────────────────────────────────────

    def connect(
        self,
        host: str,
        dbname: str,
        username: str = "",
        password: str = "",
        port: int = 5432,
        db_type: str = "postgresql",
        table: str = "",
        query: str = "",
        timeout: int = 10,
        snowflake_account: str = "",
        snowflake_warehouse: str = "",
        snowflake_schema: str = "PUBLIC",
    ) -> tuple[pd.DataFrame, dict]:
        """
        Connect and return (DataFrame, source_meta).
        Raises on failure so the caller can fall back to demo data.
        """
        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            raise ImportError(
                "sqlalchemy is required for database connections. "
                "It should already be installed — run: pip install sqlalchemy"
            )

        url = self._build_url(
            db_type, host, port, dbname, username, password,
            snowflake_account, snowflake_warehouse, snowflake_schema,
        )
        masked = self._mask_url(url, password)

        # Build engine with timeout where supported
        connect_args: dict = {}
        if db_type.lower() in ("postgresql", "postgres"):
            connect_args = {"connect_timeout": timeout}
        elif db_type.lower() in ("mssql", "sqlserver"):
            connect_args = {"timeout": timeout}

        engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

        # Verify connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        tables = self.get_tables(engine)

        # Determine what to load
        if query.strip():
            df = pd.read_sql_query(text(query.strip()), engine)
            loaded_table = f"<custom query>"
        elif table.strip() and table.strip() in tables:
            df = pd.read_sql_table(table.strip(), engine)
            loaded_table = table.strip()
        elif tables:
            # auto-pick first table
            df = pd.read_sql_table(tables[0], engine)
            loaded_table = tables[0]
        else:
            raise ValueError(
                "No tables found in the connected database. "
                "Check permissions or specify a SQL query."
            )

        source_meta = {
            "source_type":         "database",
            "platform":            "On-Premise Server" if db_type.lower() not in ("snowflake", "bigquery", "redshift") else f"Cloud Infrastructure ({db_type.title()})",
            "db_type":             db_type,
            "host":                host,
            "dbname":              dbname,
            "table":               loaded_table,
            "connection_masked":   masked,
            "available_tables":    tables,
            "databases":           [f"{dbname}.{t}" for t in tables],
            "flat_files":          [],
            "endpoints":           [],
            "label":               f"{dbname} → {loaded_table}",
            "is_demo":             False,
            "connected_at":        datetime.now().strftime("%H:%M:%S"),
        }
        return df, source_meta


# ──────────────────────────────────────────────────────────────────────────────
# FLAT FILE CONNECTOR
# ──────────────────────────────────────────────────────────────────────────────

class FlatFileConnector:
    """
    Load a flat file (local path or HTTP/S URL) into a pandas DataFrame.

    Supported formats: CSV, Parquet, JSON, Excel (.xlsx / .xls)
    format is auto-detected from the file extension when file_type="auto".
    """

    _EXT_MAP = {
        "csv":     "csv",
        "parquet": "parquet",
        "pq":      "parquet",
        "json":    "json",
        "jsonl":   "json",
        "xlsx":    "excel",
        "xls":     "excel",
        "excel":   "excel",
    }

    def _detect_type(self, path: str) -> str:
        # strip query-string and fragment, then extract extension
        cleaned = path.split("?")[0].split("#")[0]
        ext = Path(cleaned).suffix.lstrip(".").lower()
        return self._EXT_MAP.get(ext, "csv")

    def _is_url(self, path: str) -> bool:
        try:
            result = urlparse(path)
            return result.scheme in ("http", "https", "s3", "gs", "az")
        except Exception:
            return False

    def load(
        self,
        path_or_url: str,
        file_type: str = "auto",
        encoding: str = "utf-8",
        sheet_name: int | str = 0,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Load file and return (DataFrame, source_meta).
        Raises on failure.
        """
        fmt = file_type.lower() if file_type.lower() != "auto" else self._detect_type(path_or_url)
        fmt = self._EXT_MAP.get(fmt, fmt)

        try:
            if fmt == "csv":
                df = pd.read_csv(path_or_url, low_memory=False, encoding=encoding)
            elif fmt == "parquet":
                df = pd.read_parquet(path_or_url)
            elif fmt == "json":
                df = pd.read_json(path_or_url)
            elif fmt == "excel":
                df = pd.read_excel(path_or_url, sheet_name=sheet_name)
            else:
                # fallback: try CSV
                df = pd.read_csv(path_or_url, low_memory=False, encoding=encoding)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load file '{path_or_url}' as {fmt.upper()}: {exc}"
            ) from exc

        label = Path(path_or_url.split("?")[0]).name or path_or_url
        source_meta = {
            "source_type":      "flat_file",
            "path":             path_or_url,
            "file_type":        fmt.upper(),
            "label":            label,
            "available_tables": [label],
            "databases":        [],
            "flat_files":       [label],
            "endpoints":        [],
            "is_demo":          False,
            "connected_at":     datetime.now().strftime("%H:%M:%S"),
        }
        return df, source_meta


# ──────────────────────────────────────────────────────────────────────────────
# API CONNECTOR
# ──────────────────────────────────────────────────────────────────────────────

class APIConnector:
    """
    Fetch a REST API endpoint, normalize JSON → DataFrame.

    Authentication
    --------------
    Pass auth_token and the connector tries both common patterns:
      • Authorization: Bearer <token>
      • X-API-Key: <token>

    Pagination
    ----------
    Set page_limit > 1 to auto-paginate (appends each page's records).
    Set next_page_key to the JSON key that carries the next-page URL (e.g. "next").

    JSON path
    ---------
    json_path uses dot-notation to locate the array inside nested JSON.
    E.g. json_path="data.records" for { "meta": {...}, "data": { "records": [...] } }
    Leave empty if the response root is already a list or a flat object.
    """

    def _navigate(self, data, json_path: str):
        if not json_path:
            return data
        for key in json_path.split("."):
            if isinstance(data, dict):
                data = data.get(key, data)
            elif isinstance(data, list):
                break
        return data

    def _to_dataframe(self, data) -> pd.DataFrame:
        if isinstance(data, list):
            df = pd.json_normalize(data)
        elif isinstance(data, dict):
            df = pd.json_normalize([data])
        else:
            raise ValueError(
                f"Cannot convert API response type '{type(data).__name__}' to DataFrame. "
                "Expected a JSON array or object."
            )
        # Sanitize column names
        df.columns = [
            c.replace(".", "_").replace(" ", "_").replace("-", "_").lower()
            for c in df.columns
        ]
        return df

    def fetch(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        auth_token: str = "",
        header_key: str = "",
        json_path: str = "",
        method: str = "GET",
        timeout: int = 30,
        page_limit: int = 1,
        next_page_key: str = "",
        max_rows: int = 50_000,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Fetch API and return (DataFrame, source_meta).
        Raises on HTTP / network failure.
        """
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
        except ImportError:
            raise ImportError(
                "requests is required for API connections. "
                "Run: pip install requests"
            )

        # Build headers
        h = dict(headers or {})
        h.setdefault("Accept", "application/json")
        if auth_token:
            key_name = header_key.strip() if header_key.strip() else "Authorization"
            if key_name == "Authorization":
                h["Authorization"] = f"Bearer {auth_token}"
            else:
                h[key_name] = auth_token

        # Session with retries
        session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.mount("http://",  HTTPAdapter(max_retries=retry))

        all_records: list[pd.DataFrame] = []
        current_url: Optional[str] = url
        page = 0

        while current_url and page < page_limit:
            resp = session.request(
                method.upper(), current_url,
                headers=h, params=params if page == 0 else None,
                timeout=timeout,
            )
            resp.raise_for_status()

            raw = resp.json()
            data = self._navigate(raw, json_path)
            df_page = self._to_dataframe(data)
            all_records.append(df_page)

            total_rows = sum(len(d) for d in all_records)
            if total_rows >= max_rows:
                break

            # Follow next-page link if configured
            if next_page_key and isinstance(raw, dict):
                current_url = raw.get(next_page_key)
            else:
                current_url = None

            page += 1
            if current_url:
                time.sleep(0.25)   # polite delay between pages

        df = pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()
        if df.empty:
            raise ValueError(
                "API returned an empty dataset. "
                "Check the endpoint URL and JSON path."
            )

        parsed = urlparse(url)
        endpoint_label = f"{parsed.netloc}{parsed.path}"
        source_meta = {
            "source_type":      "api",
            "url":              url,
            "method":           method.upper(),
            "label":            endpoint_label,
            "available_tables": [],
            "databases":        [],
            "flat_files":       [],
            "endpoints":        [url],
            "is_demo":          False,
            "connected_at":     datetime.now().strftime("%H:%M:%S"),
        }
        return df, source_meta
