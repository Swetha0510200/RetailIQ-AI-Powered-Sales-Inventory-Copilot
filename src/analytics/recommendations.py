"""
RetailIQ Reorder & Inventory Recommendations Engine (Deterministic Python Layer)
Computes mathematically grounded reorder quantities and replenishment plans.
"""

from typing import List, Dict, Any, Optional
from src.analytics.inventory import get_inventory_status
from src.config import REORDER_TARGET_DAYS, BASELINE_DAYS, REFERENCE_DATE

def get_reorder_recommendations(store_id: Optional[int] = None, data_mode: str = "demo") -> List[Dict[str, Any]]:
    """
    Computes grounded reorder recommendations for items requiring replenishment.
    Never guesses: utilizes lead time, demand velocity, safety stock, and min batch rules.
    """
    items = get_inventory_status(store_id=store_id, data_mode=data_mode)
    reorders = []

    for item in items:
        stock = item["current_stock"]
        reorder_lvl = item["reorder_level"]
        vel = item["avg_daily_sales"]
        lead = item.get("lead_time_days") or 7
        safety = item.get("safety_stock") or 10
        min_reorder = item.get("min_reorder_qty") or 10
        cost = item.get("cost_price") or 0.0

        # Qualify for reorder if stock is below or near reorder level, or days remaining <= lead time + 5
        if stock <= reorder_lvl or item["days_remaining"] <= (lead + 5):
            cycle_demand = max(0.0, vel * (lead + REORDER_TARGET_DAYS))
            target_stock = cycle_demand + safety
            net_need = target_stock - stock
            reorder_qty = max(min_reorder, int(round(net_need)))
            if reorder_qty <= 0:
                continue

            estimated_cost = round(reorder_qty * cost, 2)

            reorders.append({
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "sku": item["sku"],
                "store_id": item["store_id"],
                "store_name": item["store_name"],
                "category_name": item["category_name"],
                "supplier_name": item.get("supplier_name", "Supplier"),
                "current_stock": stock,
                "safety_stock": safety,
                "reorder_level": reorder_lvl,
                "avg_daily_sales": vel,
                "lead_time_days": lead,
                "min_reorder_qty": min_reorder,
                "days_remaining": item["days_remaining"],
                "recommended_reorder_qty": reorder_qty,
                "unit_cost": cost,
                "estimated_investment": estimated_cost,
                "urgency": "Urgent" if item["risk_level"] == "critical_stockout" else "High" if item["risk_level"] == "low_stock" else "Normal",
                "calculation_breakdown": {
                    "formula": "reorder_qty = max(min_reorder, round((lead_time + cycle_days) * avg_sales + safety_stock - current_stock))",
                    "cycle_days": REORDER_TARGET_DAYS,
                    "target_coverage_days": lead + REORDER_TARGET_DAYS,
                    "expected_demand_during_cycle": round(cycle_demand, 1),
                    "net_shortfall": round(net_need, 1)
                },
                "assumptions": [
                    f"Average daily sales velocity ({vel} units/day) remains consistent with the prior {BASELINE_DAYS}-day baseline.",
                    f"Supplier '{item.get('supplier_name', 'Supplier')}' delivers within stated lead time of {lead} days.",
                    f"Safety stock buffer of {safety} units is preserved against demand surges."
                ]
            })

    urgency_order = {"Urgent": 0, "High": 1, "Normal": 2}
    reorders.sort(key=lambda x: (urgency_order.get(x["urgency"], 3), x["days_remaining"]))
    return reorders
