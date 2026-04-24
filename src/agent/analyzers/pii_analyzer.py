"""PII Analyzer — DQ Dimensions: Data Security & Privacy, PII Detection"""

import re
import pandas as pd
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

# PII detection patterns
PII_PATTERNS = {
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "Credit Card": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b|\b\d{16}\b",
    "Email": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "Phone": r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
    "Date of Birth": r"\b(?:19|20)\d{2}[-/]\d{2}[-/]\d{2}\b",
    "IP Address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "Passport": r"\b[A-Z]{1,2}\d{6,9}\b",
    "Driver License": r"\b[A-Z]\d{7}\b",
    "Bank Routing": r"\b[0-9]{9}\b",
    "Address": None,  # column name based only
}

# Meaningful masked examples per PII type — shows FORMAT without exposing real data
PII_MASKED_EXAMPLES = {
    "SSN":            ["***-**-6789", "***-**-4521", "***-**-3304"],
    "Credit Card":    ["**** **** **** 4242", "**** **** **** 1117", "**** **** **** 9003"],
    "Email":          ["j***n@gmail.com", "m***e@corp.org", "p***r@health.net"],
    "Phone":          ["(***) ***-7890", "(***) ***-4412", "(***) ***-2251"],
    "Date of Birth":  ["****-**-14", "****-**-07", "****-**-23"],
    "IP Address":     ["***.***.***.101", "***.***.***.45", "***.***.***.200"],
    "Passport":       ["XX****789", "YY****456", "ZZ****321"],
    "Driver License": ["X*******", "M*******", "K*******"],
    "Bank Routing":   ["*****6789", "*****4321", "*****8800"],
    "Address":        ["*** Oak Lane, ****, TX", "*** Elm St, ****, CA", "*** Main Ave, ****, NY"],
    "Name":           ["J*** D***", "M*** S***", "A*** W***"],
}

def _get_masked_samples(pii_type: str, count: int = 3) -> list:
    """Return realistic masked format examples for the detected PII type."""
    examples = PII_MASKED_EXAMPLES.get(pii_type, [f"[Protected: {pii_type}]"] * 3)
    return (examples * ((count // len(examples)) + 1))[:count]

# Column names that indicate PII (keyword matching)
PII_COLUMN_KEYWORDS = {
    "ssn": "SSN",
    "social": "SSN",
    "social_security": "SSN",
    "card_number": "Credit Card",
    "credit_card": "Credit Card",
    "cvv": "Credit Card",
    "email": "Email",
    "email_address": "Email",
    "phone": "Phone",
    "mobile": "Phone",
    "telephone": "Phone",
    "cell": "Phone",
    "date_of_birth": "Date of Birth",
    "dob": "Date of Birth",
    "birth_date": "Date of Birth",
    "birthdate": "Date of Birth",
    "ip_address": "IP Address",
    "ip": "IP Address",
    "passport": "Passport",
    "passport_no": "Passport",
    "driver_license": "Driver License",
    "routing_number": "Bank Routing",
    "routing": "Bank Routing",
    "address": "Address",
    "home_address": "Address",
    "street_address": "Address",
    "name": "Name",
    "patient_name": "Name",
    "customer_name": "Name",
    "full_name": "Name",
    "first_name": "Name",
    "last_name": "Name",
}


class PIIAnalyzer(BaseAnalyzer):
    dimension = "pii_security"
    display_name = "PII & Security"
    icon = "🔒"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        pii_found = {}  # col → pii_type

        # 1. Column name-based PII detection
        for col in df.columns:
            col_lower = col.lower().strip()
            pii_type = PII_COLUMN_KEYWORDS.get(col_lower)
            if pii_type:
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    pii_found[col] = pii_type
                    pct = self._pct(len(non_null), total)
                    issues.append(DQIssue(
                        column=col,
                        issue_type="pii_detected_by_name",
                        description=f"Column '{col}' identified as {pii_type} (PII) — contains {len(non_null):,} values",
                        affected_rows=len(non_null),
                        affected_pct=pct,
                        severity="HIGH",
                        risk_level="HIGH",
                        fix_action="mask_pii",
                        sample_values=_get_masked_samples(pii_type, min(3, len(non_null))),
                        auto_fixable=False,
                    ))

        # 2. Pattern-based PII detection in string columns
        for col in df.select_dtypes(include=["object"]).columns:
            if col in pii_found:
                continue  # already detected by name

            sample = df[col].dropna().astype(str).head(200)
            if len(sample) == 0:
                continue

            for pii_type, pattern in PII_PATTERNS.items():
                if pattern is None:
                    continue
                try:
                    matches = sample.str.contains(pattern, regex=True, na=False)
                    match_count = matches.sum()
                    if match_count > len(sample) * 0.05:  # >5% match = PII present
                        pii_found[col] = pii_type
                        full_matches = df[col].astype(str).str.contains(pattern, regex=True, na=False).sum()
                        pct = self._pct(full_matches, total)
                        issues.append(DQIssue(
                            column=col,
                            issue_type="pii_detected_by_pattern",
                            description=f"Column '{col}' contains {full_matches:,} values matching {pii_type} pattern",
                            affected_rows=full_matches,
                            affected_pct=pct,
                            severity="HIGH",
                            risk_level="HIGH",
                            fix_action="mask_pii",
                            sample_values=_get_masked_samples(pii_type, min(3, match_count)),
                            auto_fixable=False,
                        ))
                        break  # one PII type per column
                except Exception:
                    continue

        # 3. Unmasked PII summary
        pii_col_count = len(pii_found)
        total_cols = len(df.columns)

        if pii_col_count > 0:
            issues.insert(0, DQIssue(
                column="DATASET",
                issue_type="pii_exposure_summary",
                description=(
                    f"Dataset contains {pii_col_count} PII column(s) out of {total_cols} total "
                    f"({pii_col_count/total_cols*100:.1f}%). PII types: {', '.join(set(pii_found.values()))}"
                ),
                affected_rows=total,
                affected_pct=1.0,
                severity="HIGH" if pii_col_count > 3 else "MEDIUM",
                risk_level="HIGH",
                fix_action="review_and_mask_all_pii",
                sample_values=list(pii_found.keys()),
                auto_fixable=False,
            ))

        # Score: penalize for each unmasked PII field
        score = max(0.0, 100.0 - (pii_col_count * 10))

        details = {
            "pii_columns_found": pii_col_count,
            "pii_fields": pii_found,
            "pii_types": list(set(pii_found.values())),
            "total_columns": total_cols,
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
