import pandas as pd
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class EnrichmentAnalyzer(BaseAnalyzer):
    dimension = "enrichment"
    display_name = "Data Enrichment Quality"
    icon = "✨"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        for col in df.columns:
            if df[col].dtype == object and "code" not in col.lower() and "id" not in col.lower():
                mask = df[col].notna() & (df[col].astype(str).str.len() <= 2) & (df[col].astype(str).str.len() > 0)
                num = mask.sum()
                if num > 0 and col.lower() not in ["gender", "state", "status", "currency"]:
                    rate = self._pct(num, total_rows)
                    if rate > 0.10: 
                        sev = "LOW"  # Enrichment is generally low severity
                        issues.append(DQIssue(
                            column=col, issue_type="suboptimal_enrichment",
                            description="Field contains highly abbreviated or sparse text. Candidate for data enrichment/expansion.",
                            affected_rows=int(num), affected_pct=rate, severity=sev,
                            risk_level="LOW", fix_action="flag_for_enrichment",
                            sample_values=df.loc[mask, col].dropna().head(3).tolist(), auto_fixable=False
                        ))
                        
        penalty = sum([i.affected_pct * 20 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
