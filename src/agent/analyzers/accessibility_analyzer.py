import pandas as pd
import re
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class AccessibilityAnalyzer(BaseAnalyzer):
    dimension = "accessibility"
    display_name = "Data Accessibility"
    icon = "🚪"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        unreadable_pattern = re.compile(r'[^\x00-\x7F]+')
        
        for col in df.columns:
            if df[col].dtype == object:
                mask = df[col].astype(str).str.contains(unreadable_pattern, na=False) & df[col].notna()
                num = mask.sum()
                if num > 0:
                    rate = self._pct(num, total_rows)
                    sev = self._severity_from_rate(rate)
                    issues.append(
                        DQIssue(
                            column=col,
                            issue_type="unreadable_chars",
                            description="Contains non-ASCII or unreadable characters indicating corruption/accessibility faults.",
                            affected_rows=int(num),
                            affected_pct=rate,
                            severity=sev,
                            risk_level=self._risk_from_severity(sev),
                            fix_action="strip_non_ascii",
                            sample_values=df.loc[mask, col].dropna().head(3).tolist(),
                            auto_fixable=True
                        )
                    )
        
        penalty = sum([i.affected_pct * 100 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
