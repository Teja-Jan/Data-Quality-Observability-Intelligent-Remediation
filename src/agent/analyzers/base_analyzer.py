"""Base analyzer class for all DQ dimension analyzers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import pandas as pd


SEVERITY_THRESHOLDS = {
    "CRITICAL": 25,
    "HIGH": 50,
    "MEDIUM": 70,
    "LOW": 85,
    "OK": 100,
}

RISK_LEVELS = ["LOW", "MEDIUM", "HIGH"]


def score_to_severity(score: float) -> str:
    if score < 25: return "CRITICAL"
    if score < 50: return "HIGH"
    if score < 70: return "MEDIUM"
    if score < 85: return "LOW"
    return "OK"


@dataclass
class DQIssue:
    column: str
    issue_type: str
    description: str
    affected_rows: int
    affected_pct: float
    severity: str          # CRITICAL / HIGH / MEDIUM / LOW
    risk_level: str        # HIGH / MEDIUM / LOW (for fix approval)
    fix_action: str
    sample_values: list = field(default_factory=list)
    row_indices: list = field(default_factory=list)
    auto_fixable: bool = False

    def to_dict(self) -> dict:
        return {
            "column": self.column,
            "issue_type": self.issue_type,
            "description": self.description,
            "affected_rows": self.affected_rows,
            "affected_pct": round(self.affected_pct * 100, 2),
            "severity": self.severity,
            "risk_level": self.risk_level,
            "fix_action": self.fix_action,
            "sample_values": self.sample_values[:5],
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class AnalysisResult:
    dimension: str
    display_name: str
    score: float           # 0-100
    issues: list           # List[DQIssue]
    details: dict = field(default_factory=dict)
    dimension_icon: str = "📊"

    @property
    def severity(self) -> str:
        return score_to_severity(self.score)

    @property
    def issues_found(self) -> int:
        return len(self.issues)

    @property
    def critical_issues(self) -> list:
        return [i for i in self.issues if i.severity in ("CRITICAL", "HIGH")]

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "display_name": self.display_name,
            "score": round(self.score, 2),
            "severity": self.severity,
            "issues_found": self.issues_found,
            "issues": [i.to_dict() for i in self.issues],
            "details": self.details,
        }


class BaseAnalyzer(ABC):
    """Abstract base class for all DQ analyzers."""

    dimension: str = "base"
    display_name: str = "Base Analyzer"
    icon: str = "📊"

    def __init__(self, domain: str = "unknown", config: dict = None):
        self.domain = domain
        self.config = config or {}

    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> AnalysisResult:
        """Run analysis on the dataframe and return a result."""
        pass

    def _pct(self, n: int, total: int) -> float:
        return n / total if total > 0 else 0.0

    def _severity_from_rate(self, rate: float) -> str:
        if rate >= 0.30: return "CRITICAL"
        if rate >= 0.10: return "HIGH"
        if rate >= 0.05: return "MEDIUM"
        return "LOW"

    def _risk_from_severity(self, severity: str) -> str:
        return {"CRITICAL": "HIGH", "HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}.get(severity, "LOW")
