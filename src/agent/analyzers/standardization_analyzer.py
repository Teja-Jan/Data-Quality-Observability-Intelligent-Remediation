"""Standardization Analyzer — DQ Dimension: Data Standardization"""

import re
import pandas as pd
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

# Date format variants to detect mixed formats
DATE_FORMATS = [
    (r"^\d{4}-\d{2}-\d{2}$", "ISO (YYYY-MM-DD)"),
    (r"^\d{1,2}/\d{1,2}/\d{4}$", "US (MM/DD/YYYY)"),
    (r"^\d{1,2}-\d{1,2}-\d{4}$", "DD-MM-YYYY"),
    (r"^\d{4}/\d{2}/\d{2}$", "YYYY/MM/DD"),
    (r"^[A-Za-z]+ \d{1,2}, \d{4}$", "Long (Month DD, YYYY)"),
]

# Phone format variants
PHONE_PATTERNS = [
    r"^\+?1?\s?\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}$",   # (555) 555-5555
    r"^\d{10}$",                                              # 5555555555
    r"^\+\d{11,15}$",                                         # +15555555555
]

# Name columns that should use Title Case
TITLE_CASE_COLS = ["name", "patient_name", "customer_name", "physician_name",
                   "technician", "adjuster", "supplier_name", "product_name",
                   "inspector"]

# Upper case columns
UPPER_CASE_COLS = ["currency", "state", "country"]

# Date columns to check for mixed formats
DATE_COLS = ["admission_date", "discharge_date", "date_of_birth", "transaction_date",
             "policy_start", "policy_end", "claim_date", "order_date",
             "expected_delivery", "actual_delivery", "service_date", "last_updated",
             "last_inspection"]


class StandardizationAnalyzer(BaseAnalyzer):
    dimension = "standardization"
    display_name = "Data Standardization"
    icon = "📐"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        total_violations = 0

        # 1. Mixed date formats
        for col in DATE_COLS:
            if col not in df.columns:
                continue
            non_null = df[col].dropna().astype(str)
            if len(non_null) == 0:
                continue

            format_counts = {}
            for pattern, label in DATE_FORMATS:
                matched = non_null.str.match(pattern).sum()
                if matched > 0:
                    format_counts[label] = matched

            if len(format_counts) > 1:
                minority_count = sum(v for k, v in format_counts.items()
                                     if k != max(format_counts, key=format_counts.get))
                if minority_count > 0:
                    mpct = self._pct(minority_count, total)
                    sev = self._severity_from_rate(mpct)
                    format_summary = ", ".join(f"{k}: {v}" for k, v in format_counts.items())
                    issues.append(DQIssue(
                        column=col,
                        issue_type="mixed_date_formats",
                        description=f"Column '{col}' uses {len(format_counts)} date formats: {format_summary}",
                        affected_rows=minority_count,
                        affected_pct=mpct,
                        severity=sev,
                        risk_level="MEDIUM",
                        fix_action="standardize_date_format",
                        sample_values=[str(v) for v in non_null.head(5).tolist()],
                        auto_fixable=True,
                    ))
                    total_violations += minority_count

        # 2. Name casing issues
        for col in TITLE_CASE_COLS:
            if col not in df.columns:
                continue
            non_null = df[col].dropna().astype(str).str.strip()
            non_null = non_null[non_null != ""]
            if len(non_null) == 0:
                continue
            non_title = non_null[non_null != non_null.str.title()]
            if len(non_title) > 0:
                npct = self._pct(len(non_title), total)
                sev = self._severity_from_rate(npct)
                samples = non_title.head(5).tolist()
                issues.append(DQIssue(
                    column=col,
                    issue_type="case_inconsistency",
                    description=f"Column '{col}' has {len(non_title):,} values not in Title Case",
                    affected_rows=len(non_title),
                    affected_pct=npct,
                    severity=sev,
                    risk_level="LOW",
                    fix_action="apply_title_case",
                    sample_values=samples,
                    row_indices=non_null[non_null != non_null.str.title()].index.tolist(),
                    auto_fixable=True,
                ))
                total_violations += len(non_title)

        # 3. Currency / state case (should be uppercase)
        for col in UPPER_CASE_COLS:
            if col not in df.columns:
                continue
            non_null = df[col].dropna().astype(str)
            non_upper = non_null[non_null != non_null.str.upper()]
            if len(non_upper) > 0:
                npct = self._pct(len(non_upper), total)
                sev = self._severity_from_rate(npct)
                issues.append(DQIssue(
                    column=col,
                    issue_type="case_inconsistency",
                    description=f"Column '{col}' has {len(non_upper):,} values not in UPPER CASE",
                    affected_rows=len(non_upper),
                    affected_pct=npct,
                    severity=sev,
                    risk_level="LOW",
                    fix_action="apply_upper_case",
                    sample_values=non_upper.head(5).tolist(),
                    row_indices=non_upper.index.tolist(),
                    auto_fixable=True,
                ))
                total_violations += len(non_upper)

        # 4. Phone number format inconsistency
        if "phone" in df.columns:
            non_null = df["phone"].dropna().astype(str)
            # Normalize to digits-only for comparison
            digit_only = non_null.str.replace(r"[^\d]", "", regex=True)
            too_short = digit_only[digit_only.str.len() < 10]
            too_long = digit_only[digit_only.str.len() > 15]
            bad_phones = pd.concat([too_short, too_long])
            if len(bad_phones) > 0:
                bpct = self._pct(len(bad_phones), total)
                sev = self._severity_from_rate(bpct)
                issues.append(DQIssue(
                    column="phone",
                    issue_type="phone_format_violation",
                    description=f"{len(bad_phones):,} phone numbers have invalid digit counts (not 10-15 digits)",
                    affected_rows=len(bad_phones),
                    affected_pct=bpct,
                    severity=sev,
                    risk_level="MEDIUM",
                    fix_action="standardize_phone_format",
                    sample_values=bad_phones.head(5).tolist(),
                    auto_fixable=False,
                ))
                total_violations += len(bad_phones)

        # 5. Whitespace trimming issues
        for col in df.select_dtypes(include=["object"]).columns:
            non_null = df[col].dropna()
            if len(non_null) == 0:
                continue
            has_leading_trailing = (non_null.astype(str) != non_null.astype(str).str.strip()).sum()
            if has_leading_trailing > 0:
                htpct = self._pct(has_leading_trailing, total)
                if htpct > 0.01:  # only flag if >1%
                    issues.append(DQIssue(
                        column=col,
                        issue_type="whitespace_issue",
                        description=f"Column '{col}' has {has_leading_trailing:,} values with leading/trailing whitespace",
                        affected_rows=has_leading_trailing,
                        affected_pct=htpct,
                        severity="LOW",
                        risk_level="LOW",
                        fix_action="strip_whitespace",
                        auto_fixable=True,
                    ))
                    total_violations += has_leading_trailing

        penalty = min(100.0, total_violations / max(total * 3, 1) * 200)
        score = max(0.0, 100.0 - penalty)

        details = {
            "date_format_issues": sum(1 for i in issues if i.issue_type == "mixed_date_formats"),
            "case_issues": sum(1 for i in issues if i.issue_type == "case_inconsistency"),
            "phone_issues": sum(1 for i in issues if i.issue_type == "phone_format_violation"),
            "whitespace_issues": sum(1 for i in issues if i.issue_type == "whitespace_issue"),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
