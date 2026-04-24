import pandas as pd
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class IntegrityAnalyzer(BaseAnalyzer):
    dimension = "integrity"
    display_name = "Data Integrity"
    icon = "🔗"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        # Example hardcoded relational internal integrity checks:
        # e.g., if status is "Settled", "Delivered", then certain dates MUST exist
        
        if "status" in df.columns and "actual_delivery" in df.columns:
            mask = (df["status"] == "Delivered") & df["actual_delivery"].isna()
            num = mask.sum()
            if num > 0:
                rate = self._pct(num, total_rows)
                sev = "HIGH"
                issues.append(DQIssue(
                    column="actual_delivery", issue_type="integrity_violation",
                    description="Status is 'Delivered' but 'actual_delivery' is null.",
                    affected_rows=int(num), affected_pct=rate, severity=sev,
                    risk_level=self._risk_from_severity(sev), fix_action="flag_for_review",
                    sample_values=[], auto_fixable=False
                ))

        if "status" in df.columns and "discharge_date" in df.columns:
            mask = (df["status"] == "Discharged") & df["discharge_date"].isna()
            num = mask.sum()
            if num > 0:
                rate = self._pct(num, total_rows)
                sev = "HIGH"
                issues.append(DQIssue(
                    column="discharge_date", issue_type="integrity_violation",
                    description="Status is 'Discharged' but 'discharge_date' is null.",
                    affected_rows=int(num), affected_pct=rate, severity=sev,
                    risk_level=self._risk_from_severity(sev), fix_action="flag_for_review",
                    sample_values=[], auto_fixable=False
                ))
        
        if "claim_status" in df.columns and "settlement_amount" in df.columns:
            mask = (df["claim_status"] == "Settled") & df["settlement_amount"].isna()
            num = mask.sum()
            if num > 0:
                rate = self._pct(num, total_rows)
                sev = "HIGH"
                issues.append(DQIssue(
                    column="settlement_amount", issue_type="integrity_violation",
                    description="Claim status is 'Settled' but 'settlement_amount' is null.",
                    affected_rows=int(num), affected_pct=rate, severity=sev,
                    risk_level=self._risk_from_severity(sev), fix_action="flag_for_review",
                    sample_values=[], auto_fixable=False
                ))

        penalty = sum([i.affected_pct * 150 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
