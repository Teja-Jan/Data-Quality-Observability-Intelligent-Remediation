import pandas as pd
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class LineageAnalyzer(BaseAnalyzer):
    dimension = "lineage"
    display_name = "Data Lineage & Traceability"
    icon = "🛤️"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        expected_meta = ["source_system", "extracted_date", "batch_id", "record_source"]
        
        missing_meta = [m for m in expected_meta if m not in df.columns]
        if len(missing_meta) > 2:
            issues.append(DQIssue(
                column=None, issue_type="missing_traceability_metadata",
                description="Dataset lacks standard traceability lineage columns (e.g. source_system, batch_id).",
                affected_rows=len(df), affected_pct=1.0, severity="MEDIUM",
                risk_level="LOW", fix_action="add_default_lineage_metadata",
                sample_values=[], auto_fixable=True
            ))
            score = 60.0
        else:
            score = 100.0 - (len(missing_meta) * 5)
            
        return AnalysisResult(self.dimension, self.display_name, max(0.0, score), issues)
