"""
RetailIQ Intent Router & Hybrid NLU
Routes natural-language queries using Gemini 2.5/3.7 Flash with a deterministic fallback parser.
"""

import re
import json
from typing import Dict, Any, Optional
from src.utils.logging_config import logger
from src.utils.validation import validate_intent_payload

# Store keywords mapping
STORE_MAP = {
    "chennai": 1,
    "chennai central": 1,
    "karur": 2,
    "karur main": 2,
    "coimbatore": 3,
    "coimbatore mall": 3,
    "salem": 4,
    "salem junction": 4,
}

# Product keywords mapping to canonical product names
PRODUCT_KEYWORDS = [
    "wireless optical mouse", "optical mouse", "wireless mouse", "mouse",
    "ergonomic wireless keyboard", "wireless keyboard", "keyboard",
    "noise cancelling earbuds", "earbuds", "headphones",
    "stainless steel insulated flask", "insulated flask", "flask",
    "ergonomic desk mat", "desk mat",
    "premium calligraphy pen", "calligraphy pen", "fountain pen", "pen",
    "smart led desk lamp", "desk lamp", "lamp",
    "usb-c multiport hub", "usb-c hub", "hub",
    "portable bluetooth speaker", "bluetooth speaker", "speaker",
    "fast wireless charging pad", "charging pad", "charger",
    "artisanal dark roast coffee", "coffee beans", "coffee",
    "hardbound dotted journal", "journal", "notebook",
    "cast iron skillet", "iron skillet", "skillet"
]

def parse_deterministic_intent(query: str) -> Dict[str, Any]:
    """
    High-accuracy deterministic regex/keyword parser.
    Acts as a reliable offline baseline and fallback.
    """
    q = query.lower().strip()

    # 1. Check for Unsupported Queries (Restraint / Guardrail)
    unsupported_patterns = [
        r"supplier.*deliver.*tomorrow",
        r"delivery.*tomorrow",
        r"tracking.*order",
        r"weather",
        r"competitor",
        r"amazon",
        r"flipkart",
        r"stock.*market",
        r"salary",
        r"payroll",
        r"employee.*shift",
        r"inflation.*rate"
    ]
    for pat in unsupported_patterns:
        if re.search(pat, q):
            return {
                "intent": "unsupported_query",
                "confidence": 0.99,
                "entities": {},
                "unsupported_reason": "Query requests external supplier delivery tracking or third-party data not present in store sales/inventory records."
            }

    # Extract Store entity
    detected_store_id = None
    detected_store_name = None
    for s_name, s_id in STORE_MAP.items():
        if s_name in q:
            detected_store_id = s_id
            detected_store_name = s_name.title()
            break

    # Extract Product entity
    detected_product = None
    for p_keyword in PRODUCT_KEYWORDS:
        if p_keyword in q:
            detected_product = p_keyword
            break

    # Extract Time Period
    time_period = "last_30_days"
    if "this month" in q or "month" in q:
        time_period = "this_month"
    elif "last week" in q or "week" in q or "7 days" in q:
        time_period = "last_7_days"
    elif "today" in q:
        time_period = "today"

    # Intent Classification Rules
    intent = "general_data_question"

    if any(k in q for k in ["running out", "run out", "stock out", "stockout", "out of stock", "exhausted", "deplete"]):
        intent = "stock_out"
    elif any(k in q for k in ["overstock", "excess stock", "surplus", "too much stock"]):
        intent = "overstock"
    elif any(k in q for k in ["slow-moving", "slow moving", "stagnant", "sluggish", "not selling"]):
        intent = "slow_moving"
    elif any(k in q for k in ["reorder", "restock", "what should i order", "purchase order", "replenish", "replenishment"]):
        intent = "reorder_recommendation"
    elif any(k in q for k in ["spike", "surged", "surge", "unusual sales", "sales spike"]):
        intent = "sales_spike"
    elif any(k in q for k in ["sales drop", "sales drop", "sales declined", "sales fell", "sales slump", "why did sales drop", "dropped"]):
        intent = "sales_drop"
    elif any(k in q for k in ["best store", "which store", "store doing best", "store performance", "top store"]):
        intent = "store_performance"
    elif any(k in q for k in ["top product", "best seller", "best selling", "highest revenue", "top 5"]):
        intent = "top_products"
    elif detected_product and any(k in q for k in ["how did", "perform", "sales of", "revenue of"]):
        intent = "product_performance"
    elif any(k in q for k in ["sales this month", "monthly sales", "how did sales perform", "revenue this month", "sales performance"]):
        intent = "sales_performance"
    elif any(k in q for k in ["low stock", "items with low stock", "below reorder"]):
        intent = "low_stock"
    elif any(k in q for k in ["inventory health", "inventory summary", "stock summary", "total inventory"]):
        intent = "inventory_summary"
    elif any(k in q for k in ["attention", "needs attention", "what needs my attention"]):
        # What needs attention triggers composite stockout + anomaly scan
        intent = "stock_out"

    return {
        "intent": intent,
        "confidence": 0.95,
        "entities": {
            "store_id": detected_store_id,
            "store": detected_store_name,
            "product": detected_product,
            "time_period": time_period
        },
        "unsupported_reason": None
    }
