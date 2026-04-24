import pandas as pd
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class FreshnessAnalyzer(BaseAnalyzer):
    dimension = "freshness"
    display_name = "Data Freshness / Latency"
    icon = "⏰"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        for col in df.columns:
            if col.lower() in ["last_updated", "updated_at", "modified_date", "extracted_date"]:
                dates = pd.to_datetime(df[col], errors='coerce')
                mask = dates.notna() & (dates < pd.Timestamp.now() - pd.DateOffset(years=2))
                num = mask.sum()
                if num > 0:
                    rate = self._pct(num, total_rows)
                    sev = self._severity_from_rate(rate)
                    issues.append(DQIssue(
                        column=col, issue_type="stale_data",
                        description="Records are older than 2 years, violating freshness latency SLAs.",
                        affected_rows=int(num), affected_pct=rate, severity=sev,
                        risk_level=self._risk_from_severity(sev), fix_action="flag_for_archive",
                        sample_values=df.loc[mask, col].astype(str).dropna().head(3).tolist(), auto_fixable=False
                    ))
                    
        penalty = sum([i.affected_pct * 80 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
