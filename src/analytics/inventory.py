"""
RetailIQ Inventory Analytics Engine (Deterministic Python Layer)
Computes stock levels, inventory days remaining, stock-out projections, and turnover.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
from src.config import (
    REFERENCE_DATE, BASELINE_DAYS, SAFETY_STOCK_BUFFER_DAYS,
    OVERSTOCK_DAYS_THRESHOLD, SLOW_MOVING_VELOCITY_THRESHOLD
)
from src.database import get_connection, fetch_all
from src.utils.logging_config import logger

def get_inventory_status(
    store_id: Optional[int] = None,
    category_id: Optional[int] = None,
    risk_filter: Optional[str] = None,
    data_mode: str = "demo"
) -> List[Dict[str, Any]]:
    """
    Computes comprehensive deterministic inventory status for all products across stores.
    Returns calculated metrics including velocity, days remaining, and risk level.
    """
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    baseline_start = (ref_dt - timedelta(days=BASELINE_DAYS)).strftime("%Y-%m-%d")

    # Sales conditions
    sales_conditions = ["date >= ?", "date <= ?"]
    sales_params = [baseline_start, REFERENCE_DATE]
    if data_mode == "demo":
        sales_conditions.append("is_demo = 1")
    elif data_mode == "user":
        sales_conditions.append("is_demo = 0")

    sales_query = f"""
        SELECT store_id, product_id, SUM(units_sold) as total_units_baseline, COUNT(DISTINCT date) as sales_days
        FROM sales
        WHERE {" AND ".join(sales_conditions)}
        GROUP BY store_id, product_id;
    """
    sales_df = pd.read_sql_query(sales_query, conn, params=tuple(sales_params))

    # Load inventory joined with product and store metadata
    inv_query = """
        SELECT 
            i.inventory_id,
            i.store_id,
            s.name as store_name,
            s.city as store_city,
            i.product_id,
            p.sku,
            p.name as product_name,
            p.category_id,
            c.name as category_name,
            p.cost_price,
            p.selling_price,
            p.lead_time_days,
            p.min_reorder_qty,
            p.supplier_name,
            i.current_stock,
            i.reorder_level,
            i.safety_stock,
            i.last_restock_date,
            i.updated_at,
            i.is_demo
        FROM inventory i
        JOIN products p ON i.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        JOIN stores s ON i.store_id = s.store_id
    """
    params = []
    conditions = []
    if store_id:
        conditions.append("i.store_id = ?")
        params.append(store_id)
    if category_id:
        conditions.append("p.category_id = ?")
        params.append(category_id)
    if data_mode == "demo":
        conditions.append("i.is_demo = 1")
    elif data_mode == "user":
        conditions.append("i.is_demo = 0")

    if conditions:
        inv_query += " WHERE " + " AND ".join(conditions)

    inv_df = pd.read_sql_query(inv_query, conn, params=tuple(params) if params else None)
    conn.close()

    if inv_df.empty:
        return []

    # Merge sales baseline with inventory
    merged_df = pd.merge(inv_df, sales_df, on=["store_id", "product_id"], how="left")
    merged_df["total_units_baseline"] = merged_df["total_units_baseline"].fillna(0)
    
    # Calculate deterministic metrics
    merged_df["avg_daily_sales"] = (merged_df["total_units_baseline"] / float(BASELINE_DAYS)).round(2)
    
    # Calculate days of inventory remaining
    def calc_days_remaining(row):
        vel = row["avg_daily_sales"]
        stock = row["current_stock"]
        if vel <= 0.01:
            return 999.0
        return round(stock / vel, 1)

    merged_df["days_remaining"] = merged_df.apply(calc_days_remaining, axis=1)

    # Calculate estimated stock-out date
    def calc_stockout_date(days):
        if days >= 365:
            return "Stable (>1 yr)"
        target_date = ref_dt + timedelta(days=int(days))
        return target_date.strftime("%b %d, %Y")

    merged_df["estimated_stockout_date"] = merged_df["days_remaining"].apply(calc_stockout_date)

    # Classify risk level deterministically based on business rules
    def determine_risk(row):
        stock = row["current_stock"]
        vel = row["avg_daily_sales"]
        days = row["days_remaining"]
        lead_time = row["lead_time_days"]
        safety = row["safety_stock"]
        reorder_lvl = row["reorder_level"]

        # 1. Critical Stock-out: days remaining <= lead_time + safety buffer
        if days <= (lead_time + SAFETY_STOCK_BUFFER_DAYS):
            return "critical_stockout"
        # 2. Low Stock: stock <= reorder level
        elif stock <= reorder_lvl or days <= 14:
            return "low_stock"
        # 3. Overstock: days of inventory > threshold
        elif days > OVERSTOCK_DAYS_THRESHOLD and stock > 50:
            return "overstocked"
        # 4. Slow-moving: velocity below threshold with substantial days
        elif vel < SLOW_MOVING_VELOCITY_THRESHOLD and stock > safety:
            return "slow_moving"
        else:
            return "healthy"

    merged_df["risk_level"] = merged_df.apply(determine_risk, axis=1)

    # Recommended action
    def determine_action(row):
        risk = row["risk_level"]
        vel = row["avg_daily_sales"]
        lead = row["lead_time_days"]
        min_reorder = row["min_reorder_qty"]
        stock = row["current_stock"]
        safety = row["safety_stock"]

        if risk == "critical_stockout":
            target_need = int((lead + 21) * vel + safety)
            qty = max(min_reorder, target_need - stock)
            return f"Urgent: Reorder approximately {qty} units immediately (Lead time: {lead} days)."
        elif risk == "low_stock":
            target_need = int((lead + 14) * vel + safety)
            qty = max(min_reorder, target_need - stock)
            return f"Reorder {qty} units in regular replenishment cycle."
        elif risk == "overstocked":
            excess = max(0, stock - int(vel * 30))
            return f"Reduce order intake; reallocate ~{excess} units to high-demand stores or apply promotional discount."
        elif risk == "slow_moving":
            return "Bundle with complementary high-velocity items or run seasonal clearance."
        else:
            return "Maintain current replenishment schedule."

    merged_df["recommended_action"] = merged_df.apply(determine_action, axis=1)
    merged_df["stock_value"] = (merged_df["current_stock"] * merged_df["cost_price"]).round(2)
    merged_df["retail_value"] = (merged_df["current_stock"] * merged_df["selling_price"]).round(2)

    if risk_filter:
        merged_df = merged_df[merged_df["risk_level"] == risk_filter]

    risk_priority = {"critical_stockout": 0, "low_stock": 1, "slow_moving": 2, "overstocked": 3, "healthy": 4}
    merged_df["priority"] = merged_df["risk_level"].map(risk_priority)
    merged_df = merged_df.sort_values(by=["priority", "days_remaining"], ascending=[True, True])

    return merged_df.drop(columns=["priority"]).to_dict(orient="records")

def get_inventory_summary(store_id: Optional[int] = None, data_mode: str = "demo") -> Dict[str, Any]:
    """Provides high-level aggregated inventory health metrics."""
    items = get_inventory_status(store_id=store_id, data_mode=data_mode)
    if not items:
        return {
            "total_items": 0, "total_stock_units": 0, "total_cost_value": 0.0,
            "total_retail_value": 0.0, "critical_stockouts": 0, "low_stock_items": 0,
            "overstocked_items": 0, "slow_moving_items": 0, "healthy_items": 0
        }

    df = pd.DataFrame(items)
    return {
        "total_items": int(len(df)),
        "total_stock_units": int(df["current_stock"].sum()),
        "total_cost_value": round(float(df["stock_value"].sum()), 2),
        "total_retail_value": round(float(df["retail_value"].sum()), 2),
        "critical_stockouts": int((df["risk_level"] == "critical_stockout").sum()),
        "low_stock_items": int((df["risk_level"] == "low_stock").sum()),
        "overstocked_items": int((df["risk_level"] == "overstocked").sum()),
        "slow_moving_items": int((df["risk_level"] == "slow_moving").sum()),
        "healthy_items": int((df["risk_level"] == "healthy").sum())
    }
