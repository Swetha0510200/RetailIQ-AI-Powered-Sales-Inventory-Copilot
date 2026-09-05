"""
RetailIQ Data Models
Typed dataclasses for retail entities, evidence, alerts, and copilot responses.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class EvidenceItem:
    metric: str
    value: Any
    source_table: str
    date_range: str
    calculation: str
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class AlertItem:
    id: str
    alert_type: str  # stock_out, overstock, slow_moving, sales_spike, sales_drop
    severity: str    # critical, warning, info
    product_id: int
    product_name: str
    store_id: int
    store_name: str
    what_happened: str
    evidence: Dict[str, Any]
    why_it_matters: str
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CopilotResponse:
    query: str
    intent: str
    title: str
    summary: str
    details: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    data_limitations: Optional[str] = None
    is_grounded: bool = True
    model_used: str = "deterministic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "evidence": [e.to_dict() if isinstance(e, EvidenceItem) else e for e in self.evidence],
            "recommendations": self.recommendations,
            "assumptions": self.assumptions,
            "data_limitations": self.data_limitations,
            "is_grounded": self.is_grounded,
            "model_used": self.model_used
        }
