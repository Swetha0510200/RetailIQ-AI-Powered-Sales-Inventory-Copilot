"""
RetailIQ Automated Alert Engine (Deterministic Python Layer)
Scans inventory, sales velocity, and anomaly detectors to generate structured alerts.
"""

from typing import List, Dict, Any, Optional
from src.analytics.inventory import get_inventory_status
from src.analytics.sales import detect_sales_anomalies
from src.config import REFERENCE_DATE, BASELINE_DAYS, RECENT_WINDOW_DAYS

def generate_alerts(store_id: Optional[int] = None, data_mode: str = "demo") -> List[Dict[str, Any]]:
    """
    Generates all operational retail alerts with full evidence, rationale, and recommended actions.
    Sorted by severity (critical -> warning -> info).
    """
    alerts = []
    alert_counter = 1

    # 1. Scan Inventory for Stock-Out Risks and Overstock
    inv_items = get_inventory_status(store_id=store_id, data_mode=data_mode)
    for item in inv_items:
        risk = item["risk_level"]
        prod_name = item["product_name"]
        store_name = item["store_name"]
        stock = item["current_stock"]
        vel = item["avg_daily_sales"]
        days = item["days_remaining"]
        lead = item["lead_time_days"]
        safety = item["safety_stock"]

        # Critical Stock-Out Risk Alert
        if risk == "critical_stockout":
            alerts.append({
                "id": f"ALT-SO-{alert_counter:03d}",
                "alert_type": "stock_out",
                "severity": "critical",
                "product_id": item["product_id"],
                "product_name": prod_name,
                "sku": item["sku"],
                "store_id": item["store_id"],
                "store_name": store_name,
                "what_happened": f"Stock depleted to {stock} units with only {days} days of inventory remaining.",
                "evidence": {
                    "current_stock": stock,
                    "avg_daily_sales": vel,
                    "days_remaining": days,
                    "lead_time_days": lead,
                    "safety_stock": safety,
                    "baseline_period": f"Previous {BASELINE_DAYS} days (ending {REFERENCE_DATE})",
                    "source_table": "inventory, sales",
                    "formula": "days_remaining = current_stock / avg_daily_sales"
                },
                "why_it_matters": f"Stock-out is projected within {days} days, before the {lead}-day supplier delivery lead time can fulfill new inventory, causing lost sales and customer dissatisfaction.",
                "recommended_action": item["recommended_action"]
            })
            alert_counter += 1

        # Overstock Alert
        elif risk == "overstocked":
            alerts.append({
                "id": f"ALT-OS-{alert_counter:03d}",
                "alert_type": "overstock",
                "severity": "warning",
                "product_id": item["product_id"],
                "product_name": prod_name,
                "sku": item["sku"],
                "store_id": item["store_id"],
                "store_name": store_name,
                "what_happened": f"Inventory level of {stock} units represents {days} days of supply (>60-day threshold).",
                "evidence": {
                    "current_stock": stock,
                    "avg_daily_sales": vel,
                    "days_remaining": days,
                    "tied_up_capital": f"₹{item['stock_value']:,.2f}",
                    "overstock_threshold": "60 days",
                    "source_table": "inventory, sales"
                },
                "why_it_matters": f"Excess inventory locks up ₹{item['stock_value']:,.2f} in working capital and incurs warehousing carrying costs and depreciation risk.",
                "recommended_action": item["recommended_action"]
            })
            alert_counter += 1

        # Slow-Moving Alert
        elif risk == "slow_moving":
            alerts.append({
                "id": f"ALT-SM-{alert_counter:03d}",
                "alert_type": "slow_moving",
                "severity": "info",
                "product_id": item["product_id"],
                "product_name": prod_name,
                "sku": item["sku"],
                "store_id": item["store_id"],
                "store_name": store_name,
                "what_happened": f"Extremely low velocity of {vel} units/day over the last {BASELINE_DAYS} days with {stock} units idling.",
                "evidence": {
                    "current_stock": stock,
                    "avg_daily_sales": vel,
                    "days_remaining": days,
                    "category": item["category_name"],
                    "source_table": "sales, inventory"
                },
                "why_it_matters": "Low turnover drags down store inventory velocity and occupies premium display shelving.",
                "recommended_action": item["recommended_action"]
            })
            alert_counter += 1

    # 2. Scan Sales Anomalies (Spikes & Drops)
    anomalies = detect_sales_anomalies(store_id=store_id, data_mode=data_mode)
    
    # Sales Spikes
    for spike in anomalies["spikes"]:
        alerts.append({
            "id": f"ALT-SPK-{alert_counter:03d}",
            "alert_type": "sales_spike",
            "severity": "info",
            "product_id": spike["product_id"],
            "product_name": spike["product_name"],
            "sku": spike["sku"],
            "store_id": spike["store_id"],
            "store_name": spike["store_name"],
            "what_happened": f"Demand surged by +{spike['pct_change']}% in the last {RECENT_WINDOW_DAYS} days ({spike['recent_velocity']} units/day vs {spike['base_velocity']} baseline).",
            "evidence": {
                "recent_velocity": spike["recent_velocity"],
                "baseline_velocity": spike["base_velocity"],
                "velocity_ratio": spike["velocity_ratio"],
                "recent_units_sold": int(spike["recent_units"]),
                "window": f"Last {RECENT_WINDOW_DAYS} days vs Prior {BASELINE_DAYS} days",
                "source_table": "sales"
            },
            "why_it_matters": "Sudden sales acceleration indicates surging consumer demand or viral interest; risks premature stock-out if replenishment is not recalibrated.",
            "recommended_action": f"Verify inventory runway under elevated demand velocity and consider increasing next batch order size."
        })
        alert_counter += 1

    # Sales Drops
    for drop in anomalies["drops"]:
        alerts.append({
            "id": f"ALT-DRP-{alert_counter:03d}",
            "alert_type": "sales_drop",
            "severity": "warning",
            "product_id": drop["product_id"],
            "product_name": drop["product_name"],
            "sku": drop["sku"],
            "store_id": drop["store_id"],
            "store_name": drop["store_name"],
            "what_happened": f"Sales velocity declined by {abs(drop['pct_change'])}% in the last {RECENT_WINDOW_DAYS} days ({drop['recent_velocity']} units/day vs {drop['base_velocity']} baseline).",
            "evidence": {
                "recent_velocity": drop["recent_velocity"],
                "baseline_velocity": drop["base_velocity"],
                "velocity_ratio": drop["velocity_ratio"],
                "recent_units_sold": int(drop["recent_units"]),
                "window": f"Last {RECENT_WINDOW_DAYS} days vs Prior {BASELINE_DAYS} days",
                "source_table": "sales"
            },
            "why_it_matters": "Substantial unexpected drop in sales volume suggests localized stock placement friction, price sensitivity, or customer churn.",
            "recommended_action": "Check retail shelf placement, inspect product condition/expiration, and confirm if competitor discounting is affecting demand."
        })
        alert_counter += 1

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda x: severity_order.get(x["severity"], 3))
    return alerts
