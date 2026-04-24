"""Timeliness Analyzer — DQ Dimensions: Timeliness, Data Freshness, Latency"""

import pandas as pd
from datetime import datetime, timedelta
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue

# Column name → freshness SLA (days)
DEFAULT_FRESHNESS_SLA = {
    "healthcare": 7,
    "finance": 1,
    "insurance": 14,
    "supply_chain": 3,
    "automotive": 30,
}

UPDATE_COLS = ["last_updated", "updated_at", "modified_at", "timestamp",
               "transaction_date", "service_date", "admission_date", "order_date"]

DATE_COLS_FUTURE_CHECK = ["transaction_date", "service_date", "order_date",
                           "admission_date", "claim_date"]


def _parse_date(val):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


class TimelinessAnalyzer(BaseAnalyzer):
    dimension = "timeliness"
    display_name = "Data Timeliness"
    icon = "⏱️"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        today = datetime.now()

        # Get SLA from config or default
        sla_days = self.config.get("freshness_sla_days",
                                   DEFAULT_FRESHNESS_SLA.get(self.domain, 30))
        stale_threshold = today - timedelta(days=sla_days * 3)  # 3x SLA = stale
        very_stale_threshold = today - timedelta(days=365 * 2)   # 2 years = very stale

        # 1. Check last_updated / freshness columns
        update_col = None
        for col in UPDATE_COLS:
            if col in df.columns:
                update_col = col
                break

        if update_col:
            parsed_dates = df[update_col].apply(_parse_date)
            stale_mask = parsed_dates.notna() & (parsed_dates < stale_threshold)
            stale_count = stale_mask.sum()

            very_stale_mask = parsed_dates.notna() & (parsed_dates < very_stale_threshold)
            very_stale_count = very_stale_mask.sum()

            if very_stale_count > 0:
                vs_pct = self._pct(very_stale_count, total)
                sev = self._severity_from_rate(vs_pct)
                issues.append(DQIssue(
                    column=update_col,
                    issue_type="stale_records_critical",
                    description=f"{very_stale_count:,} records not updated in >2 years (freshness SLA: {sla_days} days)",
                    affected_rows=very_stale_count,
                    affected_pct=vs_pct,
                    severity=sev,
                    risk_level="HIGH",
                    fix_action="flag_for_archival_or_refresh",
                    row_indices=df[very_stale_mask].index.tolist(),
                    auto_fixable=False,
                ))
            elif stale_count > 0:
                s_pct = self._pct(stale_count, total)
                sev = self._severity_from_rate(s_pct)
                issues.append(DQIssue(
                    column=update_col,
                    issue_type="stale_records",
                    description=f"{stale_count:,} records are stale (last updated >3× SLA ago; SLA: {sla_days} days)",
                    affected_rows=stale_count,
                    affected_pct=s_pct,
                    severity=sev,
                    risk_level="MEDIUM",
                    fix_action="flag_for_refresh",
                    row_indices=df[stale_mask].index.tolist(),
                    auto_fixable=False,
                ))

        # 2. Future-dated records (dates in the future that shouldn't be)
        for col in DATE_COLS_FUTURE_CHECK:
            if col not in df.columns:
                continue
            parsed = df[col].apply(_parse_date)
            future_mask = parsed.notna() & (parsed > today)
            f_count = future_mask.sum()
            if f_count > 0:
                fpct = self._pct(f_count, total)
                sev = self._severity_from_rate(fpct)
                issues.append(DQIssue(
                    column=col,
                    issue_type="future_dated_record",
                    description=f"Column '{col}' has {f_count:,} records with future dates (max: {parsed[future_mask].max()})",
                    affected_rows=f_count,
                    affected_pct=fpct,
                    severity=sev,
                    risk_level="HIGH",
                    fix_action="flag_or_nullify_future_dates",
                    sample_values=[str(v) for v in df[col][future_mask].head(5).tolist()],
                    row_indices=df[future_mask].index.tolist(),
                    auto_fixable=False,
                ))

        # 3. Very old dates (data that predates reasonable system history)
        ancient_threshold = today - timedelta(days=365 * 10)  # 10 years ago
        for col in DATE_COLS_FUTURE_CHECK:
            if col not in df.columns:
                continue
            parsed = df[col].apply(_parse_date)
            ancient_mask = parsed.notna() & (parsed < ancient_threshold)
            a_count = ancient_mask.sum()
            if a_count > 0:
                apct = self._pct(a_count, total)
                if apct > 0.02:  # only flag if >2%
                    issues.append(DQIssue(
                        column=col,
                        issue_type="ancient_dates",
                        description=f"Column '{col}' has {a_count:,} records with dates older than 10 years",
                        affected_rows=a_count,
                        affected_pct=apct,
                        severity="LOW",
                        risk_level="LOW",
                        fix_action="flag_for_review",
                        row_indices=df[ancient_mask].index.tolist(),
                        auto_fixable=False,
                    ))

        # Score based on freshness
        stale_pct = 0
        if update_col:
            parsed_dates = df[update_col].apply(_parse_date)
            stale_overall = (parsed_dates < stale_threshold).sum()
            stale_pct = self._pct(stale_overall, total)

        future_violations = sum(i.affected_rows for i in issues if i.issue_type == "future_dated_record")
        future_pct = self._pct(future_violations, total)

        score = max(0.0, 100.0 - (stale_pct * 50) - (future_pct * 100))

        details = {
            "freshness_sla_days": sla_days,
            "stale_records": sum(i.affected_rows for i in issues if "stale" in i.issue_type),
            "future_dated": future_violations,
            "update_column_found": update_col,
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
