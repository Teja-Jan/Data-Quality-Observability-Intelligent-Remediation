"""Validity Analyzer — DQ Dimensions: Data Validity, Conformity, Constraints"""

import re
import pandas as pd
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

# Common regex patterns
PATTERNS = {
    "email": r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
    "phone": r"^[\+\d\s\(\)\-\.]{7,20}$",
    "ssn": r"^\d{3}-\d{2}-\d{4}$",
    "zip_code": r"^\d{5}(-\d{4})?$",
    "url": r"^https?://[^\s]+$",
    "ipv4": r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
    "credit_card": r"^\d{16}$",
    "vin": r"^[A-HJ-NPR-Z0-9]{17}$",
    "postal_us": r"^\d{5}$",
    "icd10": r"^[A-Z]\d{2}\.?\d{0,4}[A-Z0-9]?$",
    "date_iso": r"^\d{4}-\d{2}-\d{2}$",
    "transaction_id": r"^TXN-\d{8}$",
    "policy_id": r"^POL-\d{7}$",
    "patient_id": r"^PAT-\d{6}$",
    "order_id": r"^ORD-\d{8}$",
    "vehicle_id": r"^VEH-\d{6}$",
}

# Column name → expected pattern mapping
COL_PATTERN_MAP = {
    "email": "email",
    "phone": "phone",
    "ssn": "ssn",
    "zip_code": "zip_code",
    "zip": "zip_code",
    "postal_code": "zip_code",
    "vin": "vin",
    "diagnosis_code": "icd10",
    "icd_code": "icd10",
    "card_number": "credit_card",
    "transaction_id": "transaction_id",
    "policy_id": "policy_id",
    "patient_id": "patient_id",
    "order_id": "order_id",
    "vehicle_id": "vehicle_id",
}

# Numeric range rules: col_name → (min, max)
RANGE_RULES = {
    "age": (0, 130),
    "year": (1900, 2026),
    "mileage": (0, 2000000),
    "quantity": (1, 10000000),
    "coverage_amount": (0, 1e9),
    "premium": (0, 1e7),
    "deductible": (0, 1e6),
    "credit_limit": (0, 1e7),
    "bill_amount": (0, 50000000),
    "parts_cost": (0, 1e6),
    "labor_cost": (0, 1e6),
    "cost": (0, 1e6),
    "unit_price": (0, 1e6),
    "total_amount": (0, 1e9),
    "claim_amount": (0, 1e9),
    "settlement_amount": (0, 1e9),
}


class ValidityAnalyzer(BaseAnalyzer):
    dimension = "validity"
    display_name = "Data Validity"
    icon = "🔍"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        total_violations = 0

        # 1. Pattern validation for known columns
        for col in df.columns:
            col_lower = col.lower()
            pattern_key = COL_PATTERN_MAP.get(col_lower)
            if not pattern_key:
                continue

            pattern = PATTERNS.get(pattern_key)
            if not pattern:
                continue

            non_null = df[df[col].notna()]
            if len(non_null) == 0:
                continue

            # Convert amount columns: strip "$" before checking
            test_vals = non_null[col].astype(str).str.strip()
            invalid_mask = ~test_vals.str.match(pattern, na=False)
            invalid_count = invalid_mask.sum()

            if invalid_count > 0:
                inv_pct = self._pct(invalid_count, total)
                sev = self._severity_from_rate(inv_pct)
                samples = test_vals[invalid_mask].head(5).tolist()
                issues.append(DQIssue(
                    column=col,
                    issue_type="pattern_violation",
                    description=f"Column '{col}' has {invalid_count:,} values not matching {pattern_key} pattern",
                    affected_rows=invalid_count,
                    affected_pct=inv_pct,
                    severity=sev,
                    risk_level=self._risk_from_severity(sev),
                    fix_action="flag_or_correct_format",
                    sample_values=samples,
                    row_indices=non_null[invalid_mask].index.tolist(),
                    auto_fixable=False,
                ))
                total_violations += invalid_count

        # 2. Numeric range validation
        for col in df.columns:
            col_lower = col.lower()
            if col_lower not in RANGE_RULES:
                continue

            min_val, max_val = RANGE_RULES[col_lower]
            # Try to coerce to numeric
            try:
                numeric = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                continue

            non_null = numeric.dropna()
            if len(non_null) == 0:
                continue

            out_of_range = non_null[(non_null < min_val) | (non_null > max_val)]
            if len(out_of_range) > 0:
                oor_pct = self._pct(len(out_of_range), total)
                sev = self._severity_from_rate(oor_pct)
                issues.append(DQIssue(
                    column=col,
                    issue_type="range_violation",
                    description=f"Column '{col}' has {len(out_of_range):,} values outside range [{min_val}, {max_val}]",
                    affected_rows=len(out_of_range),
                    affected_pct=oor_pct,
                    severity=sev,
                    risk_level=self._risk_from_severity(sev),
                    fix_action="clamp_or_flag",
                    sample_values=[str(v) for v in out_of_range.head(5).tolist()],
                    row_indices=out_of_range.index.tolist(),
                    auto_fixable=False,
                ))
                total_violations += len(out_of_range)

        # 3. Type conformity: numeric stored as string with symbols
        for col in df.select_dtypes(include=["object"]).columns:
            if any(k in col.lower() for k in ["amount", "price", "cost", "balance", "revenue"]):
                dollar_mask = df[col].astype(str).str.contains(r"^\$", na=False)
                if dollar_mask.sum() > 0:
                    cnt = dollar_mask.sum()
                    pct = self._pct(cnt, total)
                    issues.append(DQIssue(
                        column=col,
                        issue_type="type_mismatch",
                        description=f"Column '{col}' has {cnt:,} values stored as strings with '$' prefix (should be numeric)",
                        affected_rows=cnt,
                        affected_pct=pct,
                        severity="HIGH",
                        risk_level="MEDIUM",
                        fix_action="strip_and_cast_numeric",
                        sample_values=df[col][dollar_mask].head(5).tolist(),
                        row_indices=df[dollar_mask].index.tolist(),
                        auto_fixable=True,
                    ))
                    total_violations += cnt

        # Score
        all_checks = total * max(1, len([c for c in df.columns
                                          if c.lower() in COL_PATTERN_MAP or c.lower() in RANGE_RULES]))
        penalty = (total_violations / all_checks * 100) if all_checks > 0 else 0
        score = max(0.0, 100.0 - penalty * 3)

        details = {
            "total_violations": total_violations,
            "columns_checked": len(issues),
            "pattern_violations": sum(1 for i in issues if i.issue_type == "pattern_violation"),
            "range_violations": sum(1 for i in issues if i.issue_type == "range_violation"),
            "type_violations": sum(1 for i in issues if i.issue_type == "type_mismatch"),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
