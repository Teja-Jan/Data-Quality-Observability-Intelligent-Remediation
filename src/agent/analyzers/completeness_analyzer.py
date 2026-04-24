"""Completeness Analyzer — DQ Dimension: Data Completeness"""

import pandas as pd
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue


class CompletenessAnalyzer(BaseAnalyzer):
    dimension = "completeness"
    display_name = "Data Completeness"
    icon = "✅"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        column_null_pcts = []

        for col in df.columns:
            null_count = df[col].isna().sum()
            null_pct = self._pct(null_count, total)
            column_null_pcts.append(null_pct)

            if null_count > 0:
                sev = self._severity_from_rate(null_pct)
                sample = df[df[col].isna()].index[:5].tolist()
                issues.append(DQIssue(
                    column=col,
                    issue_type="missing_values",
                    description=f"Column '{col}' has {null_count:,} missing values ({null_pct*100:.1f}%)",
                    affected_rows=null_count,
                    affected_pct=null_pct,
                    severity=sev,
                    risk_level=self._risk_from_severity(sev),
                    fix_action="impute_or_flag",
                    sample_values=sample,
                    row_indices=df[df[col].isna()].index.tolist(),
                    auto_fixable=(sev == "LOW"),
                ))

        # Also check for empty strings
        for col in df.select_dtypes(include=["object"]).columns:
            empty_mask = df[col].astype(str).str.strip() == ""
            empty_count = empty_mask.sum()
            if empty_count > 0:
                empty_pct = self._pct(empty_count, total)
                sev = self._severity_from_rate(empty_pct)
                issues.append(DQIssue(
                    column=col,
                    issue_type="empty_strings",
                    description=f"Column '{col}' has {empty_count:,} empty/whitespace-only values ({empty_pct*100:.1f}%)",
                    affected_rows=empty_count,
                    affected_pct=empty_pct,
                    severity=sev,
                    risk_level="LOW",
                    fix_action="replace_with_null",
                    row_indices=df[empty_mask].index.tolist(),
                    auto_fixable=True,
                ))

        # Score: weighted by column importance
        if df.empty or not column_null_pcts:
            score = 100.0
        else:
            avg_null_pct = sum(column_null_pcts) / len(column_null_pcts)
            score = max(0.0, 100.0 - (avg_null_pct * 100 * 2))  # penalize nulls

        details = {
            "total_cells": total * len(df.columns),
            "null_cells": int(df.isna().sum().sum()),
            "null_pct": round(df.isna().sum().sum() / (total * len(df.columns)) * 100, 2),
            "most_incomplete_column": df.isna().sum().idxmax() if not df.empty else None,
            "complete_columns": int((df.isna().sum() == 0).sum()),
            "incomplete_columns": int((df.isna().sum() > 0).sum()),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
