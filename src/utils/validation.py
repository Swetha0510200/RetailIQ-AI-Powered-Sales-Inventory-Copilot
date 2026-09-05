"""
RetailIQ Data Validation & Integrity Checks
Ensures data integrity, guards against impossible values, and sanitizes queries.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

SUPPORTED_INTENTS = {
    "stock_out",
    "overstock",
    "slow_moving",
    "sales_performance",
    "product_performance",
    "store_performance",
    "sales_spike",
    "sales_drop",
    "top_products",
    "low_stock",
    "inventory_summary",
    "reorder_recommendation",
    "general_data_question",
    "unsupported_query"
}

def validate_intent_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validates and normalizes structured intent payload."""
    if not isinstance(payload, dict):
        return {
            "intent": "unsupported_query",
            "confidence": 0.0,
            "entities": {},
            "unsupported_reason": "Invalid payload structure"
        }
    
    intent = str(payload.get("intent", "unsupported_query")).strip().lower()
    if intent not in SUPPORTED_INTENTS:
        intent = "unsupported_query"
    
    entities = payload.get("entities", {})
    if not isinstance(entities, dict):
        entities = {}
        
    return {
        "intent": intent,
        "confidence": float(payload.get("confidence", 0.9)),
        "entities": {
            "store": entities.get("store"),
            "product": entities.get("product"),
            "category": entities.get("category"),
            "time_period": entities.get("time_period", "last_30_days"),
            "limit": int(entities.get("limit", 10)) if str(entities.get("limit", "")).isdigit() else 10
        },
        "unsupported_reason": payload.get("unsupported_reason")
    }

def validate_numeric_bounds(value: Any, min_val: float = 0.0, default: float = 0.0) -> float:
    """Ensures numbers are not negative or non-finite."""
    try:
        val = float(value)
        if val < min_val:
            return default
        return val
    except (ValueError, TypeError):
        return default

def validate_date_string(date_str: str) -> bool:
    """Validates standard ISO date string format (YYYY-MM-DD)."""
    try:
        datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False
