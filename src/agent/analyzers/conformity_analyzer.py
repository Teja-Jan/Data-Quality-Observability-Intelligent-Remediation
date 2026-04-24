import pandas as pd
import re
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class ConformityAnalyzer(BaseAnalyzer):
    dimension = "conformity"
    display_name = "Data Conformity"
    icon = "🧩"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        email_pattern = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
        zip_pattern = re.compile(r'^\d{5}(?:-\d{4})?$')
        
        for col in df.columns:
            col_l = col.lower()
            if "email" in col_l:
                mask = df[col].notna() & ~df[col].astype(str).str.match(email_pattern)
                num = mask.sum()
                if num > 0:
                    rate = self._pct(num, total_rows)
                    sev = self._severity_from_rate(rate)
                    issues.append(DQIssue(
                        column=col, issue_type="email_format_violation",
                        description="Email addresses do not match standard conformity (user@domain.com).",
                        affected_rows=int(num), affected_pct=rate, severity=sev,
                        risk_level=self._risk_from_severity(sev), fix_action="nullify_invalid_emails",
                        sample_values=df.loc[mask, col].dropna().head(3).tolist(), auto_fixable=True
                    ))
            elif "zip" in col_l:
                mask = df[col].notna() & ~df[col].astype(str).str.match(zip_pattern)
                num = mask.sum()
                if num > 0:
                    rate = self._pct(num, total_rows)
                    sev = self._severity_from_rate(rate)
                    issues.append(DQIssue(
                        column=col, issue_type="zipcode_format_violation",
                        description="Zip codes do not conform to 5-digit or 9-digit standards.",
                        affected_rows=int(num), affected_pct=rate, severity=sev,
                        risk_level=self._risk_from_severity(sev), fix_action="clean_zipcodes",
                        sample_values=df.loc[mask, col].dropna().head(3).tolist(), auto_fixable=True
                    ))
                    
        penalty = sum([i.affected_pct * 100 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
