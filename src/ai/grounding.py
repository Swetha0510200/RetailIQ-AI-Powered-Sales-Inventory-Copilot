"""
RetailIQ Grounding & Evidence Layer
Constructs verifiable evidence objects, formulas, data lineages, and restraint explanations.
"""

from typing import List, Dict, Any, Optional
from src.models import EvidenceItem, CopilotResponse
from src.config import REFERENCE_DATE, BASELINE_DAYS, RECENT_WINDOW_DAYS

def build_evidence_item(
    metric: str,
    value: Any,
    source_table: str,
    date_range: str,
    calculation: str,
    assumptions: Optional[List[str]] = None
) -> EvidenceItem:
    """Constructs a single verifiable evidence item."""
    return EvidenceItem(
        metric=metric,
        value=value,
        source_table=source_table,
        date_range=date_range,
        calculation=calculation,
        assumptions=assumptions or []
    )

def build_unsupported_response(query: str, reason: Optional[str] = None) -> CopilotResponse:
    """
    Constructs a grounded, transparent restraint response when the user asks a question
    that cannot be answered from the available retail dataset.
    Never hallucinates or guesses.
    """
    summary = (
        "I cannot determine that from the available data. "
        "The RetailIQ dataset contains historical sales transactions, catalog pricing, "
        "and physical inventory stock levels for our 4 stores, but does not track external variables "
        "such as live supplier delivery tracking, competitor pricing, customer sentiment, or store weather."
    )
    if reason:
        summary += f"\n\n**Missing Information**: {reason}"

    return CopilotResponse(
        query=query,
        intent="unsupported_query",
        title="Query Outside Data Scope",
        summary=summary,
        details=[],
        evidence=[],
        recommendations=[
            "Integrate live supplier EDI/GPS telemetry or ERP delivery webhooks to track real-time delivery statuses.",
            "Ask questions regarding stock availability, reorder quantities, sales performance, or demand anomalies based on existing store data."
        ],
        assumptions=[
            "Data scope is strictly bounded to the local SQLite database (`stores`, `products`, `sales`, `inventory`).",
            "RetailIQ strictly refuses to fabricate or guess unrecorded business operational facts."
        ],
        data_limitations="External supplier logistics, GPS tracking, and real-time vendor dispatch signals are not present in the current database schema.",
        is_grounded=True,
        model_used="deterministic_guardrail"
    )

def format_evidence_markdown(evidence_list: List[EvidenceItem]) -> str:
    """Formats evidence items into readable markdown for the LLM prompt or UI."""
    lines = []
    for ev in evidence_list:
        lines.append(f"- **Metric**: {ev.metric} = `{ev.value}`")
        lines.append(f"  - **Source Table**: `{ev.source_table}`")
        lines.append(f"  - **Date Range**: {ev.date_range}")
        lines.append(f"  - **Formula**: {ev.calculation}")
        if ev.assumptions:
            for asm in ev.assumptions:
                lines.append(f"  - **Assumption**: {asm}")
    return "\n".join(lines)
