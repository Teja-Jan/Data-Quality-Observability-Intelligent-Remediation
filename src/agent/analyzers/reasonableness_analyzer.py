import pandas as pd
import numpy as np
from agent.analyzers.base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

class ReasonablenessAnalyzer(BaseAnalyzer):
    dimension = "reasonableness"
    display_name = "Data Reasonableness"
    icon = "⚖️"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total_rows = len(df)
        
        for col in df.select_dtypes(include=[np.number]).columns:
            if "id" in col.lower() or "zip" in col.lower() or "phone" in col.lower() or "ssn" in col.lower() or "year" in col.lower():
                continue
                
            series = df[col].dropna()
            if len(series) < 10:
                continue
                
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            
            # Using 3 * IQR for extreme outlier reasonableness bounds
            if iqr == 0:
                continue
                
            lower_bound = q1 - 3 * iqr
            upper_bound = q3 + 3 * iqr
            
            mask = df[col].notna() & ((df[col] < lower_bound) | (df[col] > upper_bound))
            num = mask.sum()
            
            if num > 0:
                rate = self._pct(num, total_rows)
                sev = "HIGH" if rate > 0.05 else "MEDIUM"
                issues.append(DQIssue(
                    column=col, issue_type="statistical_outliers",
                    description=f"Values fall outside reasonable bounds (mean +/- extreme IQR spread).",
                    affected_rows=int(num), affected_pct=rate, severity=sev,
                    risk_level=self._risk_from_severity(sev), fix_action="cap_outliers_iqr",
                    sample_values=df.loc[mask, col].dropna().head(3).tolist(), auto_fixable=True
                ))
                    
        penalty = sum([i.affected_pct * 80 for i in issues])
        score = max(0.0, 100.0 - penalty)
        return AnalysisResult(self.dimension, self.display_name, score, issues)
