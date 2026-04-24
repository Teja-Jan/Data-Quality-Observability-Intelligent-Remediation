import pandas as pd
import numpy as np
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class ReliabilityAnalyzer(BaseAnalyzer):
    dimension = "reliability"
    display_name = "Data Reliability"
    icon = "🛡️"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        for col in df.columns:
            if df[col].dtype == object:
                unreliable_vals = ["N/A", "NA", "UNKNOWN", "TEST", "UNDEFINED", "999", "99999", "00000", "TBD", "NULL", "NONE"]
                mask = df[col].astype(str).str.upper().isin(unreliable_vals) & df[col].notna()
            else:
                unreliable_vals = [-999, -9999, 99999, 999999999, 999]
                mask = df[col].isin(unreliable_vals) & df[col].notna()
                
            num = mask.sum()
            if num > 0:
                rate = self._pct(num, total_rows)
                sev = self._severity_from_rate(rate)
                issues.append(DQIssue(
                    column=col, issue_type="unreliable_default_values",
                    description="Field contains fallback/dummy indicator values representing unreliable ingestion.",
                    affected_rows=int(num), affected_pct=rate, severity=sev,
                    risk_level=self._risk_from_severity(sev), fix_action="nullify_dummy_values",
                    sample_values=df.loc[mask, col].dropna().head(3).tolist(), auto_fixable=True
                ))
                
        penalty = sum([i.affected_pct * 100 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
