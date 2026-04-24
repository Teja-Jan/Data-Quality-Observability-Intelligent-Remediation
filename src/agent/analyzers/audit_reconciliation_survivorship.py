"""
Remaining DQ Analyzers:
- Audit Analyzer (Auditability, Lineage, Reliability)
- Reconciliation Analyzer (Reconciliation, Enrichment Quality)
- Survivorship Analyzer (MDM Survivorship Rules)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from .base_analyzer import BaseAnalyzer, AnalysisResult, DQIssue


# ─── AUDIT ANALYZER ───────────────────────────────────────────────────────────

AUDIT_COLS = ["last_updated", "updated_at", "created_at", "modified_at",
              "timestamp", "audit_user", "modified_by", "created_by"]

class AuditAnalyzer(BaseAnalyzer):
    dimension = "auditability"
    display_name = "Data Auditability"
    icon = "📝"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)
        score_deductions = 0

        # 1. Check for audit timestamp columns
        audit_ts_found = [c for c in AUDIT_COLS if c in df.columns]
        if not audit_ts_found:
            issues.append(DQIssue(
                column="DATASET",
                issue_type="missing_audit_timestamp",
                description="No audit timestamp columns found (last_updated, created_at, etc.)",
                affected_rows=total,
                affected_pct=1.0,
                severity="MEDIUM",
                risk_level="MEDIUM",
                fix_action="add_audit_timestamp_column",
                auto_fixable=False,
            ))
            score_deductions += 25

        # 2. Check for ID/primary key column
        id_cols = [c for c in df.columns if c.lower() in
                   ["id", "record_id", "uuid", "guid"] or
                   c.lower().endswith("_id")]
        if not id_cols:
            issues.append(DQIssue(
                column="DATASET",
                issue_type="missing_primary_key",
                description="No primary key or unique identifier column detected",
                affected_rows=total,
                affected_pct=1.0,
                severity="HIGH",
                risk_level="HIGH",
                fix_action="add_primary_key",
                auto_fixable=False,
            ))
            score_deductions += 30

        # 3. Null timestamps where they exist
        for col in audit_ts_found:
            null_count = df[col].isna().sum()
            if null_count > 0:
                npct = self._pct(null_count, total)
                issues.append(DQIssue(
                    column=col,
                    issue_type="missing_audit_timestamp_value",
                    description=f"Audit column '{col}' has {null_count:,} missing timestamps ({npct*100:.1f}%)",
                    affected_rows=null_count,
                    affected_pct=npct,
                    severity=self._severity_from_rate(npct),
                    risk_level="MEDIUM",
                    fix_action="populate_audit_timestamps",
                    row_indices=df[df[col].isna()].index.tolist(),
                    auto_fixable=False,
                ))
                score_deductions += npct * 20

        score = max(0.0, 100.0 - score_deductions)
        details = {
            "audit_columns_found": audit_ts_found,
            "id_columns_found": id_cols,
            "auditability_gaps": len(issues),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )


# ─── RECONCILIATION ANALYZER ──────────────────────────────────────────────────

class ReconciliationAnalyzer(BaseAnalyzer):
    dimension = "reconciliation"
    display_name = "Data Reconciliation"
    icon = "⚖️"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)

        # 1. Check for completeness of amount fields vs count
        amount_cols = [c for c in df.columns if any(k in c.lower()
                        for k in ["amount", "price", "cost", "balance", "premium"])]
        for col in amount_cols:
            numeric = pd.to_numeric(df[col], errors="coerce")
            non_null = numeric.dropna()
            if len(non_null) < total * 0.5:
                # More than 50% missing for an amount column = reconciliation risk
                pct_missing = self._pct(total - len(non_null), total)
                issues.append(DQIssue(
                    column=col,
                    issue_type="amount_reconciliation_gap",
                    description=f"Amount column '{col}' is missing {pct_missing*100:.1f}% of values — reconciliation impossible",
                    affected_rows=total - len(non_null),
                    affected_pct=pct_missing,
                    severity="HIGH",
                    risk_level="HIGH",
                    fix_action="require_source_refresh",
                    auto_fixable=False,
                ))

        # 2. Row count check (schema audit: expected minimum)
        if total < 10:
            issues.append(DQIssue(
                column="DATASET",
                issue_type="insufficient_row_count",
                description=f"Dataset has only {total} rows — may be incomplete or from partial load",
                affected_rows=total,
                affected_pct=1.0,
                severity="HIGH",
                risk_level="HIGH",
                fix_action="verify_full_data_load",
                auto_fixable=False,
            ))

        # 3. Enrichment quality: derived/calculated columns accuracy
        derived_pairs = [
            ("total_amount", "quantity", "unit_price", "product"),
            ("cost", "parts_cost", "labor_cost", "sum"),
        ]
        for derived_col, a_col, b_col, op in derived_pairs:
            if not all(c in df.columns for c in [derived_col, a_col, b_col]):
                continue
            d = pd.to_numeric(df[derived_col], errors="coerce")
            a = pd.to_numeric(df[a_col], errors="coerce")
            b = pd.to_numeric(df[b_col], errors="coerce")
            valid = d.notna() & a.notna() & b.notna()
            if op == "product":
                expected = a * b
            else:
                expected = a + b
            tol = expected.abs() * 0.01 + 0.01
            mismatches = valid & ((d - expected).abs() > tol)
            mcount = mismatches.sum()
            if mcount > 0:
                mpct = self._pct(mcount, total)
                issues.append(DQIssue(
                    column=derived_col,
                    issue_type="enrichment_accuracy",
                    description=f"Derived column '{derived_col}' has {mcount:,} values that don't match expected {op} of {a_col}×{b_col}",
                    affected_rows=mcount,
                    affected_pct=mpct,
                    severity="HIGH",
                    risk_level="HIGH",
                    fix_action=f"recalculate_{op}",
                    auto_fixable=True,
                ))

        penalty = sum(i.affected_rows / max(total, 1) for i in issues) * 50
        score = max(0.0, 100.0 - penalty)

        details = {
            "amount_columns_checked": len(amount_cols),
            "reconciliation_gaps": len([i for i in issues if "reconciliation" in i.issue_type]),
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )


# ─── SURVIVORSHIP ANALYZER ────────────────────────────────────────────────────

class SurvivorshipAnalyzer(BaseAnalyzer):
    dimension = "survivorship"
    display_name = "Survivorship (MDM)"
    icon = "🏆"

    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        issues = []
        total = len(df)

        # Identify potential entity key columns
        entity_keys = []
        for col in df.columns:
            col_lower = col.lower()
            if any(k in col_lower for k in ["customer_id", "patient_id", "supplier_id",
                                             "account_id", "vehicle_id"]):
                entity_keys.append(col)

        if not entity_keys:
            return AnalysisResult(
                dimension=self.dimension,
                display_name=self.display_name,
                score=100.0,
                issues=[],
                details={"message": "No entity key columns detected for MDM analysis"},
                dimension_icon=self.icon,
            )

        total_survivors = 0
        for key_col in entity_keys:
            non_null = df[key_col].dropna()
            duplicated_entities = non_null[non_null.duplicated(keep=False)]

            if len(duplicated_entities) == 0:
                continue

            dup_entities = duplicated_entities.unique()
            conflict_count = 0
            survivorship_candidates = []

            for entity_id in dup_entities[:50]:  # check first 50 for performance
                entity_rows = df[df[key_col] == entity_id]
                if len(entity_rows) < 2:
                    continue

                # Check for conflicting values in key fields
                check_cols = [c for c in df.columns if c != key_col and
                              any(k in c.lower() for k in ["name", "address", "phone",
                                                            "email", "status", "date"])]
                for col in check_cols[:5]:
                    unique_vals = entity_rows[col].dropna().unique()
                    if len(unique_vals) > 1:
                        conflict_count += 1
                        survivorship_candidates.append({
                            "entity": str(entity_id),
                            "conflict_field": col,
                            "values": [str(v) for v in unique_vals[:3]],
                        })
                        break

            if conflict_count > 0:
                cpct = self._pct(conflict_count, len(dup_entities))
                total_survivors += conflict_count
                issues.append(DQIssue(
                    column=key_col,
                    issue_type="survivorship_conflict",
                    description=(
                        f"{conflict_count} entities with duplicate '{key_col}' have conflicting attribute values — "
                        f"survivorship rules needed to select best record"
                    ),
                    affected_rows=conflict_count,
                    affected_pct=cpct,
                    severity="HIGH",
                    risk_level="HIGH",
                    fix_action="apply_survivorship_rules",
                    sample_values=[f"{c['entity']}: {c['conflict_field']} has {c['values']}" for c in survivorship_candidates[:3]],
                    auto_fixable=False,
                ))

            # Golden record recommendation
            dup_count = len(duplicated_entities)
            dpct = self._pct(dup_count, total)
            if dpct > 0.01:
                issues.append(DQIssue(
                    column=key_col,
                    issue_type="missing_golden_record",
                    description=f"{dup_count:,} rows share duplicate '{key_col}' — no golden record designation",
                    affected_rows=dup_count,
                    affected_pct=dpct,
                    severity="MEDIUM",
                    risk_level="HIGH",
                    fix_action="designate_golden_record",
                    auto_fixable=False,
                ))

        score = max(0.0, 100.0 - (total_survivors / max(total, 1)) * 200)

        details = {
            "entity_key_columns": entity_keys,
            "survivorship_conflicts": total_survivors,
        }

        return AnalysisResult(
            dimension=self.dimension,
            display_name=self.display_name,
            score=round(score, 2),
            issues=issues,
            details=details,
            dimension_icon=self.icon,
        )
