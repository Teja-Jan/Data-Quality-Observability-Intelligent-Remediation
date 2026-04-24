"""Profiling Analyzer — DQ Dimension: Data Profiling"""

import numpy as np
import pandas as pd
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue


class ProfilingAnalyzer(BaseAnalyzer):
    dimension = "profiling"
    display_name = "Data Profiling"
    icon = "📊"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        profile = {}

        for col in df.columns:
            col_profile = {
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isna().sum()),
                "null_pct": round(df[col].isna().sum() / total * 100, 2) if total > 0 else 0,
                "unique_count": int(df[col].nunique()),
                "unique_pct": round(df[col].nunique() / total * 100, 2) if total > 0 else 0,
            }

            if pd.api.types.is_numeric_dtype(df[col]):
                num = df[col].dropna()
                if len(num) > 0:
                    col_profile.update({
                        "min": float(num.min()),
                        "max": float(num.max()),
                        "mean": float(num.mean()),
                        "median": float(num.median()),
                        "std": float(num.std()),
                        "q25": float(num.quantile(0.25)),
                        "q75": float(num.quantile(0.75)),
                    })
            else:
                str_col = df[col].dropna().astype(str)
                if len(str_col) > 0:
                    top_val = str_col.value_counts().idxmax() if len(str_col) > 0 else None
                    col_profile.update({
                        "top_value": top_val,
                        "top_freq": int(str_col.value_counts().iloc[0]) if len(str_col) > 0 else 0,
                        "min_length": int(str_col.str.len().min()),
                        "max_length": int(str_col.str.len().max()),
                        "avg_length": round(float(str_col.str.len().mean()), 2),
                    })

            # Flag high-cardinality string columns
            if (str(df[col].dtype) == "object" and
                    col_profile["unique_pct"] > 90 and
                    not any(k in col.lower() for k in ["id", "name", "address", "email",
                                                        "phone", "ssn", "vin", "description",
                                                        "card", "routing"])):
                issues.append(DQIssue(
                    column=col,
                    issue_type="high_cardinality",
                    description=f"Column '{col}' has unusually high cardinality ({col_profile['unique_pct']:.1f}% unique) — may need review",
                    affected_rows=0,
                    affected_pct=0,
                    severity="LOW",
                    risk_level="LOW",
                    fix_action="review_column_design",
                    auto_fixable=False,
                ))

            # Flag constant or near-constant columns
            if col_profile["unique_count"] == 1:
                issues.append(DQIssue(
                    column=col,
                    issue_type="constant_column",
                    description=f"Column '{col}' has only 1 unique value — may be a constant or error",
                    affected_rows=total,
                    affected_pct=1.0,
                    severity="MEDIUM",
                    risk_level="LOW",
                    fix_action="review_or_drop_column",
                    auto_fixable=False,
                ))

            # Flag all-null columns
            if col_profile["null_count"] == total:
                issues.append(DQIssue(
                    column=col,
                    issue_type="all_null_column",
                    description=f"Column '{col}' is entirely NULL — candidate for removal",
                    affected_rows=total,
                    affected_pct=1.0,
                    severity="HIGH",
                    risk_level="MEDIUM",
                    fix_action="drop_column",
                    auto_fixable=False,
                ))

            profile[col] = col_profile

        # Score based on column health
        health_issues = len([i for i in issues if i.severity in ("HIGH", "CRITICAL")])
        score = max(0.0, 100.0 - health_issues * 10)

        # Compute overall dataset stats
        details = {
            "total_rows": total,
            "total_columns": len(df.columns),
            "numeric_columns": int(df.select_dtypes(include=[np.number]).shape[1]),
            "string_columns": int(df.select_dtypes(include=["object"]).shape[1]),
            "date_columns": int(df.select_dtypes(include=["datetime"]).shape[1]),
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1_048_576, 2),
            "null_rate_overall": round(df.isna().sum().sum() / (total * len(df.columns)) * 100, 2),
            "column_profiles": profile,
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
