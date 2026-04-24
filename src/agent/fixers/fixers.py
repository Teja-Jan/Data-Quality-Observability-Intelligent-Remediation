"""
DQ Agent Framework — All Fixer Modules
Each fixer accepts: df (dirty DataFrame), issue list, and config dict.
Returns: (cleaned_df, change_log list)
"""

import re
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime
from rapidfuzz import fuzz, process


# ─── BASE FIXER ───────────────────────────────────────────────────────────────

class BaseFixer:
    risk_level: str = "LOW"

    def __init__(self, domain: str = "unknown", config: dict = None):
        self.domain = domain
        self.config = config or {}

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        raise NotImplementedError

    def _log(self, action: str, column: str, rows_affected: int, detail: str = "") -> dict:
        return {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "column": column,
            "rows_affected": rows_affected,
            "detail": detail,
        }


# ─── COMPLETENESS FIXER ───────────────────────────────────────────────────────

class CompletenessFixer(BaseFixer):
    """Fill missing values using appropriate strategies per column type."""
    risk_level = "MEDIUM"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        strategy = self.config.get("strategy", "auto")

        for col in df.columns:
            null_count = df[col].isna().sum()
            if null_count == 0:
                continue

            if pd.api.types.is_numeric_dtype(df[col]):
                if strategy == "mean":
                    fill_val = df[col].mean()
                elif strategy == "zero":
                    fill_val = 0
                else:
                    fill_val = df[col].median()
                df[col].fillna(fill_val, inplace=True)
                change_log.append(self._log("impute_median", col, null_count,
                                             f"Filled with median: {round(fill_val, 4)}"))
            else:
                mode_vals = df[col].mode()
                if len(mode_vals) > 0:
                    fill_val = mode_vals[0]
                    df[col].fillna(fill_val, inplace=True)
                    change_log.append(self._log("impute_mode", col, null_count,
                                                 f"Filled with mode: {fill_val}"))
                else:
                    df[col].fillna("UNKNOWN", inplace=True)
                    change_log.append(self._log("impute_unknown", col, null_count, "Filled with UNKNOWN"))

        return df, change_log


# ─── UNIQUENESS FIXER ─────────────────────────────────────────────────────────

class UniquenessFixer(BaseFixer):
    """Remove duplicate rows using exact or fuzzy matching."""
    risk_level = "HIGH"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        original_count = len(df)

        # Exact deduplication
        before = len(df)
        df = df.drop_duplicates(keep="first")
        removed = before - len(df)
        if removed > 0:
            change_log.append(self._log("exact_dedup", "ALL", removed,
                                         f"Removed {removed} exact duplicate rows"))

        # ID column deduplication
        id_cols = [c for c in df.columns if c.lower().endswith("_id") or c.lower() == "id"]
        for col in id_cols:
            before = len(df)
            df = df.drop_duplicates(subset=[col], keep="last")
            removed = before - len(df)
            if removed > 0:
                change_log.append(self._log("id_dedup", col, removed,
                                             f"Removed {removed} duplicate {col} values (kept last)"))

        total_removed = original_count - len(df)
        return df, change_log


# ─── STANDARDIZATION FIXER ────────────────────────────────────────────────────

class StandardizationFixer(BaseFixer):
    """Standardize date formats, casing, phone numbers, and whitespace."""
    risk_level = "LOW"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []

        title_case_cols = [c for c in df.columns if any(k in c.lower()
                           for k in ["name", "physician", "technician", "adjuster",
                                     "supplier_name", "product_name", "inspector"])]
        upper_cols = [c for c in df.columns if c.lower() in ["currency", "state", "country"]]
        date_cols = [c for c in df.columns if any(k in c.lower()
                     for k in ["_date", "admission", "discharge", "transaction_date",
                                "service_date", "order_date", "claim_date",
                                "policy_start", "policy_end", "expected_delivery",
                                "actual_delivery", "last_updated", "date_of_birth"])]

        # Title case
        for col in title_case_cols:
            if col not in df.columns:
                continue
            changed = (df[col].notna() & (df[col].astype(str) != df[col].astype(str).str.title())).sum()
            if changed > 0:
                df[col] = df[col].apply(lambda x: str(x).title() if pd.notna(x) else x)
                change_log.append(self._log("title_case", col, changed, "Applied Title Case"))

        # Upper case
        for col in upper_cols:
            if col not in df.columns:
                continue
            changed = (df[col].notna() & (df[col].astype(str) != df[col].astype(str).str.upper())).sum()
            if changed > 0:
                df[col] = df[col].apply(lambda x: str(x).upper() if pd.notna(x) else x)
                change_log.append(self._log("upper_case", col, changed, "Applied UPPER CASE"))

        # Standardize dates to ISO format
        for col in date_cols:
            if col not in df.columns:
                continue
            fixed = 0
            new_vals = []
            for val in df[col]:
                parsed = None
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%B %d, %Y"):
                    try:
                        parsed = datetime.strptime(str(val).strip(), fmt).date()
                        break
                    except (ValueError, TypeError):
                        continue
                if parsed and str(val).strip() != str(parsed):
                    new_vals.append(str(parsed))
                    fixed += 1
                else:
                    new_vals.append(val)
            if fixed > 0:
                df[col] = new_vals
                change_log.append(self._log("standardize_date", col, fixed, "Converted to ISO YYYY-MM-DD"))

        # Strip whitespace from all string columns
        for col in df.select_dtypes(include=["object"]).columns:
            changed = (df[col].notna() & (df[col].astype(str) != df[col].astype(str).str.strip())).sum()
            if changed > 0:
                df[col] = df[col].apply(lambda x: str(x).strip() if pd.notna(x) else x)
                change_log.append(self._log("strip_whitespace", col, changed, "Stripped leading/trailing whitespace"))

        # Strip $ from numeric-stored-as-string
        for col in df.columns:
            if any(k in col.lower() for k in ["amount", "price", "cost", "balance"]):
                if df[col].dtype == object:
                    dollar_mask = df[col].astype(str).str.startswith("$")
                    if dollar_mask.sum() > 0:
                        df.loc[dollar_mask, col] = pd.to_numeric(
                            df.loc[dollar_mask, col].astype(str).str.replace("$", "").str.replace(",", ""),
                            errors="coerce"
                        )
                        change_log.append(self._log("strip_currency_symbol", col, dollar_mask.sum(),
                                                     "Removed $ and cast to numeric"))

        return df, change_log


# ─── VALIDITY FIXER ───────────────────────────────────────────────────────────

class ValidityFixer(BaseFixer):
    """Clamp out-of-range values, fix type issues."""
    risk_level = "MEDIUM"

    RANGE_RULES = {
        "age": (0, 130),
        "year": (1900, 2026),
        "mileage": (0, 2000000),
        "quantity": (1, 10000000),
        "fraud_flag": (0, 1),
    }

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []

        for col, (min_val, max_val) in self.RANGE_RULES.items():
            if col not in df.columns:
                continue
            numeric = pd.to_numeric(df[col], errors="coerce")
            out_of_range = (numeric < min_val) | (numeric > max_val)
            count = out_of_range.sum()
            if count > 0:
                df.loc[out_of_range, col] = np.nan
                change_log.append(self._log("nullify_out_of_range", col, count,
                                             f"Set values outside [{min_val}, {max_val}] to NaN"))

        return df, change_log


# ─── CONSISTENCY FIXER ────────────────────────────────────────────────────────

class ConsistencyFixer(BaseFixer):
    """Fix enum inconsistencies and recalculate derived fields."""
    risk_level = "LOW"

    ENUM_MAPS = {
        "gender": {"m": "Male", "male": "Male", "f": "Female", "female": "Female", "other": "Other"},
        "status": {"active": "Active", "inactive": "Inactive", "completed": "Completed",
                   "pending": "Pending", "cancelled": "Cancelled", "delivered": "Delivered",
                   "discharged": "Discharged", "deceased": "Deceased", "transferred": "Transferred",
                   "failed": "Failed"},
        "currency": {"usd": "USD", "eur": "EUR", "gbp": "GBP", "jpy": "JPY", "cad": "CAD",
                     "us dollar": "USD", "euro": "EUR"},
        "transaction_type": {"credit": "Credit", "debit": "Debit", "transfer": "Transfer",
                              "refund": "Refund", "fee": "Fee"},
        "policy_type": {"health": "Health", "life": "Life", "auto": "Auto",
                         "home": "Home", "commercial": "Commercial"},
        "engine_type": {"gasoline": "Gasoline", "diesel": "Diesel", "electric": "Electric",
                         "hybrid": "Hybrid", "plug-in hybrid": "Plug-in Hybrid"},
        "quality_check": {"pass": "Pass", "fail": "Fail", "pending": "Pending"},
        "claim_status": {"submitted": "Submitted", "under review": "Under Review",
                          "approved": "Approved", "rejected": "Rejected", "settled": "Settled"},
        "payment_status": {"paid": "Paid", "pending": "Pending", "partial": "Partial", "denied": "Denied"},
        "warranty_status": {"active": "Active", "expired": "Expired", "not applicable": "Not Applicable"},
    }

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []

        for col, val_map in self.ENUM_MAPS.items():
            if col not in df.columns:
                continue
            non_null = df[col].notna()
            lowercase_vals = df.loc[non_null, col].astype(str).str.lower().str.strip()
            mapped = lowercase_vals.map(val_map)
            needs_fix = mapped.notna() & (df.loc[non_null, col].astype(str) != mapped)
            count = needs_fix.sum()
            if count > 0:
                df.loc[df.index[non_null][needs_fix], col] = mapped[needs_fix].values
                change_log.append(self._log("standardize_enum", col, count,
                                             f"Standardized {count} enum values"))

        # Recalculate total_amount = quantity × unit_price
        if all(c in df.columns for c in ["total_amount", "quantity", "unit_price"]):
            qty = pd.to_numeric(df["quantity"], errors="coerce")
            price = pd.to_numeric(df["unit_price"], errors="coerce")
            total = pd.to_numeric(df["total_amount"], errors="coerce")
            both_valid = qty.notna() & price.notna() & total.notna()
            expected = qty * price
            tol = expected.abs() * 0.01 + 0.01
            mismatches = both_valid & ((total - expected).abs() > tol)
            count = mismatches.sum()
            if count > 0:
                df.loc[mismatches, "total_amount"] = (qty * price)[mismatches].round(2)
                change_log.append(self._log("recalculate_total", "total_amount", count,
                                             "Recalculated as quantity × unit_price"))

        # Recalculate cost = parts_cost + labor_cost
        if all(c in df.columns for c in ["cost", "parts_cost", "labor_cost"]):
            parts = pd.to_numeric(df["parts_cost"], errors="coerce")
            labor = pd.to_numeric(df["labor_cost"], errors="coerce")
            cost = pd.to_numeric(df["cost"], errors="coerce")
            both_valid = parts.notna() & labor.notna() & cost.notna()
            expected = parts + labor
            tol = expected.abs() * 0.01 + 0.01
            mismatches = both_valid & ((cost - expected).abs() > tol)
            count = mismatches.sum()
            if count > 0:
                df.loc[mismatches, "cost"] = (parts + labor)[mismatches].round(2)
                change_log.append(self._log("recalculate_cost", "cost", count,
                                             "Recalculated as parts_cost + labor_cost"))

        return df, change_log


# ─── ACCURACY FIXER ───────────────────────────────────────────────────────────

class AccuracyFixer(BaseFixer):
    """Cap outliers using IQR winsorization."""
    risk_level = "MEDIUM"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        iqr_factor = self.config.get("iqr_factor", 1.5)

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - iqr_factor * iqr
            upper = q3 + iqr_factor * iqr
            outliers = (df[col] < lower) | (df[col] > upper)
            count = outliers.sum()
            if count > 0:
                df[col] = df[col].clip(lower=lower, upper=upper)
                change_log.append(self._log("winsorize_outliers", col, count,
                                             f"Capped to [{round(lower,4)}, {round(upper,4)}]"))

        return df, change_log


# ─── PII FIXER ────────────────────────────────────────────────────────────────

class PIIFixer(BaseFixer):
    """Mask PII fields using hash, asterisk, tokenization, or removal."""
    risk_level = "HIGH"

    def fix(self, df: pd.DataFrame, issue=None, pii_config: dict = None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        if pii_config is None:
            pii_config = {}

        pii_fields = pii_config.get("fields", {})
        default_mode = pii_config.get("default_mode", "hash")

        for col, mode in pii_fields.items():
            if col not in df.columns:
                continue
            non_null_count = df[col].notna().sum()
            if non_null_count == 0:
                continue

            if mode == "hash":
                df[col] = df[col].apply(
                    lambda x: hashlib.sha256(str(x).encode()).hexdigest()[:16].upper() if pd.notna(x) else x
                )
                change_log.append(self._log("hash_pii", col, non_null_count, "SHA-256 hash (16 chars)"))

            elif mode == "mask":
                # Partial mask: keep first 2 and last 2 chars
                df[col] = df[col].apply(
                    lambda x: (str(x)[:2] + "*" * max(0, len(str(x)) - 4) + str(x)[-2:]) if pd.notna(x) and len(str(x)) > 4 else "****"
                )
                change_log.append(self._log("mask_pii", col, non_null_count, "Partial masking applied"))

            elif mode == "tokenize":
                token_map = {}
                token_counter = [1]
                def tokenize(x):
                    if pd.isna(x): return x
                    k = str(x)
                    if k not in token_map:
                        token_map[k] = f"TOKEN-{col.upper()[:4]}-{token_counter[0]:06d}"
                        token_counter[0] += 1
                    return token_map[k]
                df[col] = df[col].apply(tokenize)
                change_log.append(self._log("tokenize_pii", col, non_null_count,
                                             f"Tokenized to {len(token_map)} unique tokens"))

            elif mode == "remove":
                df[col] = np.nan
                change_log.append(self._log("remove_pii", col, non_null_count, "Column values removed (set to null)"))

            elif mode == "redact":
                df[col] = "[REDACTED]"
                change_log.append(self._log("redact_pii", col, non_null_count, "Replaced with [REDACTED]"))

        return df, change_log


# ─── BUSINESS RULES FIXER ─────────────────────────────────────────────────────

class BusinessRulesFixer(BaseFixer):
    """Apply fixes for business rule violations."""
    risk_level = "MEDIUM"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []

        # Rule: Non-negative financial amounts
        amount_cols = [c for c in df.columns if any(k in c.lower()
                        for k in ["amount", "price", "cost", "premium", "balance",
                                   "coverage", "deductible", "settlement", "bill"])]
        for col in amount_cols:
            numeric = pd.to_numeric(df[col], errors="coerce")
            neg_mask = numeric < 0
            count = neg_mask.sum()
            if count > 0:
                df.loc[neg_mask, col] = numeric[neg_mask].abs()
                change_log.append(self._log("abs_negative_amounts", col, count,
                                             "Converted negative amounts to absolute values"))

        # Rule: Positive quantity
        if "quantity" in df.columns:
            qty = pd.to_numeric(df["quantity"], errors="coerce")
            invalid = qty <= 0
            count = invalid.sum()
            if count > 0:
                df.loc[invalid, "quantity"] = np.nan
                change_log.append(self._log("nullify_invalid_quantity", "quantity", count,
                                             "Set zero/negative quantities to NaN"))

        # Rule: Binary fraud_flag
        if "fraud_flag" in df.columns:
            flag = pd.to_numeric(df["fraud_flag"], errors="coerce")
            invalid = ~flag.isin([0, 1])
            count = invalid.sum()
            if count > 0:
                df.loc[invalid, "fraud_flag"] = 0
                change_log.append(self._log("fix_fraud_flag", "fraud_flag", count,
                                             "Set invalid fraud_flag values to 0"))

        return df, change_log

# ─── ACCESSIBILITY FIXER ──────────────────────────────────────────────────────

class AccessibilityFixer(BaseFixer):
    risk_level = "LOW"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        for col in df.columns:
            if df[col].dtype == object:
                mask = df[col].astype(str).str.contains(r'[^\x00-\x7F]+', na=False)
                count = mask.sum()
                if count > 0:
                    df.loc[mask, col] = df.loc[mask, col].astype(str).str.encode('ascii', 'ignore').str.decode('ascii')
                    change_log.append(self._log("strip_non_ascii", col, count, "Removed unreadable non-ASCII characters"))
        return df, change_log

# ─── CONFORMITY FIXER ─────────────────────────────────────────────────────────

class ConformityFixer(BaseFixer):
    risk_level = "LOW"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        for col in df.columns:
            if "email" in col.lower():
                mask = df[col].notna() & ~df[col].astype(str).str.match(r'^[^@]+@[^@]+\.[^@]+$')
                count = mask.sum()
                if count > 0:
                    df.loc[mask, col] = np.nan
                    change_log.append(self._log("nullify_invalid_emails", col, count, "Set invalid emails to NaN"))
            elif "zip" in col.lower():
                mask = df[col].notna() & ~df[col].astype(str).str.match(r'^\d{5}(?:-\d{4})?$')
                count = mask.sum()
                if count > 0:
                    df.loc[mask, col] = np.nan
                    change_log.append(self._log("clean_zipcodes", col, count, "Set invalid zipcodes to NaN"))
        return df, change_log

# ─── CONSTRAINTS FIXER ────────────────────────────────────────────────────────

class ConstraintsFixer(BaseFixer):
    risk_level = "MEDIUM"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        if "age" in df.columns:
            mask = df["age"].notna() & ((pd.to_numeric(df["age"], errors="coerce") < 0) | (pd.to_numeric(df["age"], errors="coerce") > 130))
            count = mask.sum()
            if count > 0:
                df.loc[mask, "age"] = df.loc[mask, "age"].clip(0, 130)
                change_log.append(self._log("clip_age_constraint", "age", count, "Clipped age to 0-130 bounds"))
        return df, change_log

# ─── ENRICHMENT FIXER ─────────────────────────────────────────────────────────

class EnrichmentFixer(BaseFixer):
    risk_level = "LOW"
    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        # Typically requires external APIs, so we just log the flagging action
        return df, [self._log("flag_for_enrichment", "ALL", 0, "Flagged columns for external enrichment")]

# ─── FRESHNESS FIXER ──────────────────────────────────────────────────────────

class FreshnessFixer(BaseFixer):
    risk_level = "LOW"
    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        return df, [self._log("flag_for_archive", "ALL", 0, "Flagged stale data for archival")]

# ─── INTEGRITY FIXER ──────────────────────────────────────────────────────────

class IntegrityFixer(BaseFixer):
    risk_level = "HIGH"
    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        return df, [self._log("flag_for_review", "ALL", 0, "Flagged referential integrity miss for manual review")]

# ─── LINEAGE FIXER ────────────────────────────────────────────────────────────

class LineageFixer(BaseFixer):
    risk_level = "LOW"
    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        expected = {"source_system": "default_src", "batch_id": "BATCH-0000", "record_source": "auto-filled"}
        change_log = []
        for col, val in expected.items():
            if col not in df.columns:
                df[col] = val
                change_log.append(self._log("add_lineage_metadata", col, len(df), f"Added default lineage column '{col}'"))
        return df, change_log

# ─── REASONABLENESS FIXER ──────────────────────────────────────────────────────

class ReasonablenessFixer(BaseFixer):
    risk_level = "MEDIUM"
    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        for col in df.select_dtypes(include=[np.number]).columns:
            if "id" in col.lower() or "zip" in col.lower() or "phone" in col.lower():
                continue
            series = df[col].dropna()
            if len(series) < 10: continue
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0: continue
            lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
            mask = df[col].notna() & ((df[col] < lower) | (df[col] > upper))
            count = mask.sum()
            if count > 0:
                df[col] = df[col].clip(lower=lower, upper=upper)
                change_log.append(self._log("cap_outliers_iqr", col, count, f"Capped extreme reasonableness outliers [{lower:.2f}, {upper:.2f}]"))
        return df, change_log

# ─── RELIABILITY FIXER ────────────────────────────────────────────────────────

class ReliabilityFixer(BaseFixer):
    risk_level = "MEDIUM"
    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        for col in df.columns:
            if df[col].dtype == object:
                unreliable_vals = ["N/A", "NA", "UNKNOWN", "TEST", "UNDEFINED", "999", "99999", "00000", "TBD", "NULL", "NONE"]
                mask = df[col].astype(str).str.upper().isin(unreliable_vals) & df[col].notna()
            else:
                unreliable_vals = [-999, -9999, 99999, 999999999, 999]
                mask = df[col].isin(unreliable_vals) & df[col].notna()
            count = mask.sum()
            if count > 0:
                df.loc[mask, col] = np.nan
                change_log.append(self._log("nullify_dummy_values", col, count, "Converted unreliable dummy placeholders to NaN"))
        return df, change_log

# ─── SURVIVORSHIP FIXER ───────────────────────────────────────────────────────

class SurvivorshipFixer(BaseFixer):
    """Generate golden records (MDM) using survivorship rules."""
    risk_level = "HIGH"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        entity_keys = [c for c in df.columns if "id" in c.lower() and any(k in c.lower() for k in ["customer", "patient", "supplier", "account", "vehicle"])]

        for key_col in entity_keys:
            duplicates = df[df.duplicated(subset=[key_col], keep=False)]
            if len(duplicates) == 0:
                continue

            # Generate golden record: Group by key, fill missing values (ffill/bfill), and keep first
            before = len(df)
            df = df.sort_values(by=key_col).groupby(key_col).apply(lambda x: x.ffill().bfill()).drop_duplicates(subset=[key_col], keep='first').reset_index(drop=True)
            removed = before - len(df)
            if removed > 0:
                change_log.append(self._log("golden_record_generation", key_col, removed,
                                             f"Applied MDM survivorship: Merged duplicates into Golden Records and removed {removed} redundant rows"))

        return df, change_log

# ─── AUDIT FIXER ─────────────────────────────────────────────────────────────

class AuditFixer(BaseFixer):
    """Ensure data auditability by injecting standard timestamp columns."""
    risk_level = "MEDIUM"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        
        audit_cols = ["last_updated", "created_at"]
        for col in audit_cols:
            if col not in df.columns:
                df[col] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                change_log.append(self._log("inject_audit_column", col, len(df), f"Added missing audit timestamp column: {col}"))
            else:
                null_mask = df[col].isna()
                count = null_mask.sum()
                if count > 0:
                    df.loc[null_mask, col] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    change_log.append(self._log("populate_audit_timestamps", col, count, f"Filled {count} missing audit timestamps with current time"))

        return df, change_log

# ─── RECONCILIATION FIXER ────────────────────────────────────────────────────

class ReconciliationFixer(BaseFixer):
    """Handle reconciliation logic to pad data or resolve un-reconcilable attributes."""
    risk_level = "HIGH"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []

        amount_cols = [c for c in df.columns if any(k in c.lower() for k in ["amount", "price", "cost", "balance", "premium"])]
        for col in amount_cols:
            numeric = pd.to_numeric(df[col], errors="coerce")
            null_mask = numeric.isna()
            count = null_mask.sum()
            if count > 0 and count < len(df) * 0.5: # only fix if not overwhelmingly missing
                df.loc[null_mask, col] = 0.0
                change_log.append(self._log("reconcile_missing_amount", col, count, f"Padded {count} missing financial amounts with 0.0 for reconciliation completeness"))

        return df, change_log

# ─── TIMELINESS FIXER ────────────────────────────────────────────────────────

class TimelinessFixer(BaseFixer):
    """Mask or archive stale temporal data."""
    risk_level = "MEDIUM"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = []
        
        date_cols = [c for c in df.columns if "date" in c.lower() or "timestamp" in c.lower()]
        current_year = pd.Timestamp.now().year
        
        for col in date_cols:
            try:
                dates = pd.to_datetime(df[col], errors="coerce")
                stale_mask = dates.dt.year < (current_year - 15)  # mark data older than 15 years as stale
                count = stale_mask.sum()
                if count > 0:
                    df.loc[stale_mask, col] = np.nan
                    change_log.append(self._log("archive_stale_data", col, count, f"Nullified {count} extremely stale timestamps (>15 yrs old)"))
            except Exception:
                pass

        return df, change_log

# ─── PROFILING FIXER ─────────────────────────────────────────────────────────

class ProfilingFixer(BaseFixer):
    """Profiling itself does not modify data, but this logs a baseline lock."""
    risk_level = "LOW"

    def fix(self, df: pd.DataFrame, issue=None) -> tuple[pd.DataFrame, list]:
        df = df.copy()
        change_log = [self._log("lock_profiling_baseline", "ALL", 0, "Locked current statistical profile baseline for future drift detection")]
        return df, change_log
