"""Uniqueness Analyzer — DQ Dimensions: Data Uniqueness & Deduplication"""

import pandas as pd
from rapidfuzz import fuzz
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue


class UniquenessAnalyzer(BaseAnalyzer):
    dimension = "uniqueness"
    display_name = "Data Uniqueness"
    icon = "🔁"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)

        # 1. Exact duplicate rows
        dup_mask = df.duplicated(keep="first")
        dup_count = dup_mask.sum()
        if dup_count > 0:
            dup_pct = self._pct(dup_count, total)
            sev = self._severity_from_rate(dup_pct)
            issues.append(DQIssue(
                column="ALL",
                issue_type="exact_duplicates",
                description=f"{dup_count:,} exact duplicate rows detected ({dup_pct*100:.1f}%)",
                affected_rows=dup_count,
                affected_pct=dup_pct,
                severity=sev,
                risk_level="HIGH",
                fix_action="drop_duplicates",
                row_indices=df[dup_mask].index.tolist(),
                auto_fixable=False,
            ))

        # 2. ID column uniqueness checks (columns ending in _id)
        id_cols = [c for c in df.columns if c.lower().endswith("_id") or c.lower() == "id"]
        for col in id_cols:
            non_null = df[col].dropna()
            if len(non_null) == 0:
                continue
            dup_ids = non_null[non_null.duplicated(keep=False)]
            if len(dup_ids) > 0:
                dup_pct = self._pct(len(dup_ids), total)
                sev = self._severity_from_rate(dup_pct)
                samples = dup_ids.value_counts().head(5).index.tolist()
                issues.append(DQIssue(
                    column=col,
                    issue_type="duplicate_ids",
                    description=f"Column '{col}' has {len(dup_ids):,} duplicate ID values ({dup_pct*100:.1f}%)",
                    affected_rows=len(dup_ids),
                    affected_pct=dup_pct,
                    severity=sev,
                    risk_level="HIGH",
                    fix_action="deduplicate_ids",
                    sample_values=[str(s) for s in samples],
                    row_indices=df[df[col].isin(dup_ids)].index.tolist(),
                    auto_fixable=False,
                ))

        # 3. Near-duplicate detection on string columns (name, address)
        name_cols = [c for c in df.columns if any(k in c.lower() for k in
                     ["name", "address", "customer", "patient", "supplier"])]
        for col in name_cols[:2]:  # limit for performance
            non_null_vals = df[col].dropna().astype(str).tolist()
            if len(non_null_vals) < 10:
                continue
            # Sample up to 300 values for fuzzy check
            sample_size = min(300, len(non_null_vals))
            sample = non_null_vals[:sample_size]
            threshold = self.config.get("fuzzy_threshold", 90)
            near_dups = []
            for i in range(len(sample)):
                for j in range(i + 1, min(i + 20, len(sample))):
                    ratio = fuzz.ratio(sample[i], sample[j])
                    if threshold <= ratio < 100:
                        near_dups.append((sample[i], sample[j], ratio))
                        if len(near_dups) >= 20:
                            break
                if len(near_dups) >= 20:
                    break

            if near_dups:
                n_near = len(near_dups)
                near_pct = self._pct(n_near * 2, total)
                issues.append(DQIssue(
                    column=col,
                    issue_type="near_duplicates",
                    description=f"Column '{col}' contains ~{n_near} near-duplicate pairs (fuzzy match ≥{threshold}%)",
                    affected_rows=n_near * 2,
                    affected_pct=near_pct,
                    severity="MEDIUM",
                    risk_level="HIGH",
                    fix_action="fuzzy_deduplication",
                    sample_values=[f"'{a}' ≈ '{b}' ({r}%)" for a, b, r in near_dups[:3]],
                    auto_fixable=False,
                ))

        # Score
        dup_penalty = (dup_count / total * 60) if total > 0 else 0
        id_penalty = sum(i.affected_pct for i in issues if i.issue_type == "duplicate_ids") * 30
        score = max(0.0, 100.0 - dup_penalty - id_penalty)

        details = {
            "total_rows": total,
            "exact_duplicates": dup_count,
            "unique_rows": total - dup_count,
            "uniqueness_rate": round((1 - dup_count / total) * 100, 2) if total > 0 else 100,
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
