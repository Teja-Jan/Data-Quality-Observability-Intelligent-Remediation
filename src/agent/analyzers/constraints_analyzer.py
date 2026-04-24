import pandas as pd
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class ConstraintsAnalyzer(BaseAnalyzer):
    dimension = "constraints"
    display_name = "Data Constraints Check"
    icon = "🚧"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        if "age" in df.columns:
            mask = df["age"].notna() & ((pd.to_numeric(df["age"], errors="coerce") < 0) | (pd.to_numeric(df["age"], errors="coerce") > 130))
            num = mask.sum()
            if num > 0:
                rate = self._pct(num, total_rows)
                sev = self._severity_from_rate(rate)
                issues.append(DQIssue(
                    column="age", issue_type="constraint_violation_age",
                    description="Age violates logical constraints (must be 0-130).",
                    affected_rows=int(num), affected_pct=rate, severity=sev,
                    risk_level=self._risk_from_severity(sev), fix_action="clip_age_constraint",
                    sample_values=df.loc[mask, "age"].dropna().head(3).tolist(), auto_fixable=True
                ))
                
        for col in df.columns:
            if any(term in col.lower() for term in ["cost", "price", "amount", "premium", "quantity", "mileage"]):
                numeric_series = pd.to_numeric(df[col], errors="coerce")
                mask = numeric_series.notna() & (numeric_series < 0)
                num = mask.sum()
                if num > 0:
                    rate = self._pct(num, total_rows)
                    sev = self._severity_from_rate(rate)
                    issues.append(DQIssue(
                        column=col, issue_type="constraint_violation_negative_value",
                        description=f"{col} violates constraints (cannot be negative).",
                        affected_rows=int(num), affected_pct=rate, severity=sev,
                        risk_level=self._risk_from_severity(sev), fix_action="absolute_value",
                        sample_values=df.loc[mask, col].dropna().head(3).tolist(), auto_fixable=True
                    ))

        penalty = sum([i.affected_pct * 100 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
