"""Consistency Analyzer — DQ Dimensions: Consistency, Integrity, Reconciliation"""

import pandas as pd
from datetime import datetime
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

# Cross-field date pair rules: (start_col, end_col) → end must be >= start
DATE_PAIR_RULES = [
    ("admission_date", "discharge_date"),
    ("policy_start", "policy_end"),
    ("order_date", "expected_delivery"),
    ("order_date", "actual_delivery"),
    ("start_date", "end_date"),
]

# Calculation rules: (result_col, [(factor_col, multiplier)]) → result should equal sum
CALC_RULES = [
    ("total_amount", [("quantity", 1), ("unit_price", 1)], "product"),        # total = qty × price
    ("cost", [("parts_cost", 1), ("labor_cost", 1)], "sum"),                   # cost = parts + labor
]

# Enum consistency maps (canonical values)
ENUM_FIELDS = {
    "gender": {"male", "female", "other", "unknown"},
    "currency": {"usd", "eur", "gbp", "jpy", "cad", "aud"},
    "status": {"active", "inactive", "completed", "pending", "cancelled",
               "failed", "delivered", "ordered", "discharged", "deceased",
               "transferred"},
    "payment_status": {"paid", "pending", "partial", "denied"},
    "claim_status": {"submitted", "under review", "approved", "rejected", "settled"},
    "policy_type": {"health", "life", "auto", "home", "commercial"},
    "engine_type": {"gasoline", "diesel", "electric", "hybrid", "plug-in hybrid"},
    "warranty_status": {"active", "expired", "not applicable"},
    "quality_check": {"pass", "fail", "pending"},
    "transaction_type": {"credit", "debit", "transfer", "refund", "fee"},
}


def _try_parse_date(val) -> datetime | None:
    if pd.isna(val):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            continue
    return None


class ConsistencyAnalyzer(BaseAnalyzer):
    dimension = "consistency"
    display_name = "Data Consistency"
    icon = "🔄"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        total_violations = 0

        # 1. Date pair consistency (end >= start)
        for start_col, end_col in DATE_PAIR_RULES:
            if start_col not in df.columns or end_col not in df.columns:
                continue
            starts = df[start_col].apply(_try_parse_date)
            ends = df[end_col].apply(_try_parse_date)
            both_valid = starts.notna() & ends.notna()
            violations = both_valid & (ends < starts)
            vcount = violations.sum()
            if vcount > 0:
                vpct = self._pct(vcount, total)
                sev = self._severity_from_rate(vpct)
                issues.append(DQIssue(
                    column=f"{start_col}↔{end_col}",
                    issue_type="date_order_violation",
                    description=f"{vcount:,} records have '{end_col}' before '{start_col}'",
                    affected_rows=vcount,
                    affected_pct=vpct,
                    severity=sev,
                    risk_level="HIGH",
                    fix_action="swap_dates_or_nullify",
                    row_indices=df[violations].index.tolist(),
                    auto_fixable=False,
                ))
                total_violations += vcount

        # 2. Calculation consistency
        for rule in CALC_RULES:
            result_col, factor_cols, op = rule
            if result_col not in df.columns:
                continue
            factor_a, factor_b = factor_cols[0][0], factor_cols[1][0]
            if factor_a not in df.columns or factor_b not in df.columns:
                continue

            result_num = pd.to_numeric(df[result_col], errors="coerce")
            a_num = pd.to_numeric(df[factor_a], errors="coerce")
            b_num = pd.to_numeric(df[factor_b], errors="coerce")
            all_valid = result_num.notna() & a_num.notna() & b_num.notna()

            if op == "product":
                expected = a_num * b_num
            else:
                expected = a_num + b_num

            tolerance = expected.abs() * 0.01 + 0.01  # 1% tolerance
            mismatches = all_valid & ((result_num - expected).abs() > tolerance)
            mcount = mismatches.sum()
            if mcount > 0:
                mpct = self._pct(mcount, total)
                sev = self._severity_from_rate(mpct)
                issues.append(DQIssue(
                    column=result_col,
                    issue_type="calculation_inconsistency",
                    description=f"{mcount:,} records: '{result_col}' doesn't match {op}({factor_a}, {factor_b})",
                    affected_rows=mcount,
                    affected_pct=mpct,
                    severity=sev,
                    risk_level="HIGH",
                    fix_action=f"recalculate_{op}",
                    row_indices=df[mismatches].index.tolist(),
                    auto_fixable=True,
                ))
                total_violations += mcount

        # 3. Categorical value inconsistency (case variants)
        for col in df.columns:
            col_lower = col.lower()
            canonical = ENUM_FIELDS.get(col_lower)
            if canonical is None:
                continue
            non_null = df[col].dropna().astype(str)
            invalid_vals = non_null[~non_null.str.lower().isin(canonical)]
            if len(invalid_vals) > 0:
                inv_pct = self._pct(len(invalid_vals), total)
                sev = self._severity_from_rate(inv_pct)
                samples = invalid_vals.value_counts().head(5).index.tolist()
                issues.append(DQIssue(
                    column=col,
                    issue_type="enum_inconsistency",
                    description=f"Column '{col}' has {len(invalid_vals):,} values with unexpected casing/format variants",
                    affected_rows=len(invalid_vals),
                    affected_pct=inv_pct,
                    severity=sev,
                    risk_level="LOW",
                    fix_action="standardize_enum_values",
                    sample_values=samples,
                    row_indices=invalid_vals.index.tolist(),
                    auto_fixable=True,
                ))
                total_violations += len(invalid_vals)

        # 4. Referential integrity: claim_date within policy period (if both exist)
        if all(c in df.columns for c in ["claim_date", "policy_start", "policy_end"]):
            claim_dt = df["claim_date"].apply(_try_parse_date)
            start_dt = df["policy_start"].apply(_try_parse_date)
            end_dt = df["policy_end"].apply(_try_parse_date)
            all_valid = claim_dt.notna() & start_dt.notna() & end_dt.notna()
            outside = all_valid & ((claim_dt < start_dt) | (claim_dt > end_dt))
            ocount = outside.sum()
            if ocount > 0:
                opct = self._pct(ocount, total)
                issues.append(DQIssue(
                    column="claim_date",
                    issue_type="referential_integrity",
                    description=f"{ocount:,} claims have claim_date outside the policy period",
                    affected_rows=ocount,
                    affected_pct=opct,
                    severity="HIGH",
                    risk_level="HIGH",
                    fix_action="flag_for_review",
                    row_indices=df[outside].index.tolist(),
                    auto_fixable=False,
                ))
                total_violations += ocount

        penalty = min(100.0, total_violations / max(total, 1) * 200)
        score = max(0.0, 100.0 - penalty)

        details = {
            "date_violations": sum(1 for i in issues if i.issue_type == "date_order_violation"),
            "calc_violations": sum(1 for i in issues if i.issue_type == "calculation_inconsistency"),
            "enum_violations": sum(1 for i in issues if i.issue_type == "enum_inconsistency"),
            "referential_violations": sum(1 for i in issues if i.issue_type == "referential_integrity"),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
