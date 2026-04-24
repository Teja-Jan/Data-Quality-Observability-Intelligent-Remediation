"""Accuracy Analyzer — DQ Dimensions: Data Accuracy, Reasonableness, Outliers"""

import numpy as np
import pandas as pd
from scipy import stats
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue


class AccuracyAnalyzer(BaseAnalyzer):
    dimension = "accuracy"
    display_name = "Data Accuracy"
    icon = "🎯"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        total_outlier_cells = 0

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        # Also try to coerce object cols that might be numeric
        for col in df.select_dtypes(include=["object"]).columns:
            if any(k in col.lower() for k in ["amount", "price", "cost", "balance", "revenue",
                                               "quantity", "age", "mileage", "premium",
                                               "coverage", "deductible", "credit"]):
                coerced = pd.to_numeric(df[col].astype(str).str.replace(r"[,$]", "", regex=True),
                                        errors="coerce")
                if coerced.notna().sum() > len(df) * 0.5:
                    df = df.copy()
                    df[col] = coerced
                    if col not in numeric_cols:
                        numeric_cols.append(col)

        iqr_factor = self.config.get("outlier_iqr_factor", 1.5)
        zscore_threshold = self.config.get("outlier_zscore_threshold", 3.0)

        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 10:
                continue

            # IQR method
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue

            lower = q1 - iqr_factor * iqr
            upper = q3 + iqr_factor * iqr
            outlier_mask = (series < lower) | (series > upper)
            outlier_count = outlier_mask.sum()

            # Z-score method (secondary)
            z_scores = np.abs(stats.zscore(series, nan_policy="omit"))
            z_outliers = (z_scores > zscore_threshold).sum()

            # Use the more conservative count (intersection)
            if outlier_count > 0:
                out_pct = self._pct(outlier_count, len(series))
                # Only flag if meaningful (>0.5%)
                if out_pct > 0.005:
                    sev = self._severity_from_rate(out_pct)
                    outlier_vals = series[outlier_mask]
                    issues.append(DQIssue(
                        column=col,
                        issue_type="statistical_outlier",
                        description=(
                            f"Column '{col}' has {outlier_count:,} outliers "
                            f"(IQR: [{lower:.2f}, {upper:.2f}], "
                            f"actual range: [{series.min():.2f}, {series.max():.2f}])"
                        ),
                        affected_rows=outlier_count,
                        affected_pct=out_pct,
                        severity=sev,
                        risk_level="MEDIUM",
                        fix_action="cap_winsorize_outliers",
                        sample_values=[str(round(v, 4)) for v in outlier_vals.head(5)],
                        row_indices=series[outlier_mask].index.tolist(),
                        auto_fixable=False,
                    ))
                    total_outlier_cells += outlier_count

        # Impossible value checks
        impossible_rules = [
            ("age", lambda s: s < 0, "Negative age values"),
            ("age", lambda s: s > 130, "Age > 130 (unreasonably high)"),
            ("mileage", lambda s: s < 0, "Negative mileage"),
            ("year", lambda s: s < 1900, "Vehicle year before 1900"),
            ("year", lambda s: s > 2026, "Vehicle year in the future"),
            ("quantity", lambda s: s < 0, "Negative quantity"),
            ("fraud_flag", lambda s: ~s.isin([0, 1]), "Fraud flag not binary (0 or 1)"),
        ]

        for col, condition_fn, desc in impossible_rules:
            if col not in df.columns:
                continue
            try:
                numeric_col = pd.to_numeric(df[col], errors="coerce").dropna()
                violated = numeric_col[condition_fn(numeric_col)]
                if len(violated) > 0:
                    vpct = self._pct(len(violated), total)
                    issues.append(DQIssue(
                        column=col,
                        issue_type="impossible_value",
                        description=f"{len(violated):,} records: {desc}",
                        affected_rows=len(violated),
                        affected_pct=vpct,
                        severity="HIGH",
                        risk_level="HIGH",
                        fix_action="flag_or_correct",
                        sample_values=[str(v) for v in violated.head(5)],
                        row_indices=violated.index.tolist(),
                        auto_fixable=False,
                    ))
                    total_outlier_cells += len(violated)
            except Exception:
                continue

        # Score
        total_numeric_cells = sum(df[c].count() for c in numeric_cols)
        penalty = (total_outlier_cells / max(total_numeric_cells, 1)) * 150
        score = max(0.0, 100.0 - penalty)

        details = {
            "numeric_columns_analyzed": len(numeric_cols),
            "total_outliers": total_outlier_cells,
            "outlier_columns": sum(1 for i in issues if i.issue_type == "statistical_outlier"),
            "impossible_value_columns": sum(1 for i in issues if i.issue_type == "impossible_value"),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
