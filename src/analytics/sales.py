"""
RetailIQ Sales Analytics Engine (Deterministic Python Layer)
Calculates revenue, profit, velocity, store performance, and sales anomalies (spikes/drops).
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
from src.config import (
    REFERENCE_DATE, BASELINE_DAYS, RECENT_WINDOW_DAYS,
    SALES_SPIKE_RATIO, SALES_DROP_RATIO
)
from src.database import get_connection

def _build_mode_clause(data_mode: str, alias: str = "") -> str:
    """Helper to build is_demo SQL filter based on data_mode."""
    prefix = f"{alias}." if alias else ""
    if data_mode == "demo":
        return f" AND {prefix}is_demo = 1"
    elif data_mode == "user":
        return f" AND {prefix}is_demo = 0"
    return ""

def get_kpis(store_id: Optional[int] = None, days: int = 30, data_mode: str = "demo") -> Dict[str, Any]:
    """Calculates top-level KPI metrics for the specified period and prior comparison period."""
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    current_start = (ref_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    prior_start = (ref_dt - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    prior_end = (ref_dt - timedelta(days=days + 1)).strftime("%Y-%m-%d")

    mode_clause = _build_mode_clause(data_mode)
    store_clause = " AND store_id = ?" if store_id else ""
    params_curr = [current_start, REFERENCE_DATE] + ([store_id] if store_id else [])
    
    curr_sql = f"""
        SELECT 
            COALESCE(SUM(revenue), 0) as total_revenue,
            COALESCE(SUM(units_sold), 0) as total_units,
            COALESCE(SUM(profit), 0) as total_profit,
            COUNT(DISTINCT product_id) as active_skus
        FROM sales
        WHERE date >= ? AND date <= ? {store_clause} {mode_clause};
    """
    curr_df = pd.read_sql_query(curr_sql, conn, params=params_curr)
    curr_rev = float(curr_df["total_revenue"].iloc[0])
    curr_units = int(curr_df["total_units"].iloc[0])
    curr_profit = float(curr_df["total_profit"].iloc[0])
    curr_skus = int(curr_df["active_skus"].iloc[0])
    margin_pct = round((curr_profit / curr_rev * 100), 1) if curr_rev > 0 else 0.0

    # Prior period comparison metrics
    params_prior = [prior_start, prior_end] + ([store_id] if store_id else [])
    prior_sql = f"""
        SELECT 
            COALESCE(SUM(revenue), 0) as total_revenue,
            COALESCE(SUM(units_sold), 0) as total_units
        FROM sales
        WHERE date >= ? AND date <= ? {store_clause} {mode_clause};
    """
    prior_df = pd.read_sql_query(prior_sql, conn, params=params_prior)
    prior_rev = float(prior_df["total_revenue"].iloc[0])
    prior_units = int(prior_df["total_units"].iloc[0])

    rev_growth = round(((curr_rev - prior_rev) / prior_rev * 100), 1) if prior_rev > 0 else 0.0
    units_growth = round(((curr_units - prior_units) / prior_units * 100), 1) if prior_units > 0 else 0.0

    conn.close()

    return {
        "period_days": days,
        "date_range": f"{current_start} to {REFERENCE_DATE}",
        "total_revenue": round(curr_rev, 2),
        "total_units": curr_units,
        "total_profit": round(curr_profit, 2),
        "profit_margin_pct": margin_pct,
        "active_skus": curr_skus,
        "revenue_growth_pct": rev_growth,
        "units_growth_pct": units_growth
    }

def get_sales_trends(store_id: Optional[int] = None, days: int = 30, data_mode: str = "demo") -> List[Dict[str, Any]]:
    """Returns daily time-series sales trend for charts."""
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    start_date = (ref_dt - timedelta(days=days)).strftime("%Y-%m-%d")

    mode_clause = _build_mode_clause(data_mode)
    store_clause = " AND store_id = ?" if store_id else ""
    params = [start_date, REFERENCE_DATE] + ([store_id] if store_id else [])

    query = f"""
        SELECT 
            date,
            SUM(revenue) as revenue,
            SUM(units_sold) as units,
            SUM(profit) as profit
        FROM sales
        WHERE date >= ? AND date <= ? {store_clause} {mode_clause}
        GROUP BY date
        ORDER BY date ASC;
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        return []

    return [
        {
            "date": row["date"],
            "revenue": round(float(row["revenue"]), 2),
            "units": int(row["units"]),
            "profit": round(float(row["profit"]), 2)
        }
        for _, row in df.iterrows()
    ]

def get_top_products(
    store_id: Optional[int] = None,
    limit: int = 5,
    days: int = 30,
    by: str = "revenue",
    data_mode: str = "demo"
) -> List[Dict[str, Any]]:
    """Returns top performing products by revenue or units sold."""
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    start_date = (ref_dt - timedelta(days=days)).strftime("%Y-%m-%d")

    mode_clause = _build_mode_clause(data_mode, "s")
    store_clause = " AND s.store_id = ?" if store_id else ""
    params = [start_date, REFERENCE_DATE] + ([store_id] if store_id else []) + [limit]
    order_col = "total_revenue" if by == "revenue" else "total_units"

    query = f"""
        SELECT 
            p.product_id,
            p.sku,
            p.name as product_name,
            c.name as category_name,
            SUM(s.units_sold) as total_units,
            ROUND(SUM(s.revenue), 2) as total_revenue,
            ROUND(SUM(s.profit), 2) as total_profit,
            ROUND(AVG(s.units_sold), 2) as avg_daily_velocity
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE s.date >= ? AND s.date <= ? {store_clause} {mode_clause}
        GROUP BY p.product_id, p.sku, p.name, c.name
        ORDER BY {order_col} DESC
        LIMIT ?;
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df.to_dict(orient="records")

def get_store_performance(days: int = 30, data_mode: str = "demo") -> List[Dict[str, Any]]:
    """Compares sales, revenue, profit and stock health across all physical stores."""
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    start_date = (ref_dt - timedelta(days=days)).strftime("%Y-%m-%d")

    store_mode = _build_mode_clause(data_mode, "st")
    sales_mode = _build_mode_clause(data_mode, "s")

    query = f"""
        SELECT 
            st.store_id,
            st.code,
            st.name as store_name,
            st.city,
            st.manager_name,
            COALESCE(SUM(s.revenue), 0) as total_revenue,
            COALESCE(SUM(s.units_sold), 0) as total_units,
            COALESCE(SUM(s.profit), 0) as total_profit
        FROM stores st
        LEFT JOIN sales s ON st.store_id = s.store_id AND s.date >= ? AND s.date <= ? {sales_mode}
        WHERE 1=1 {store_mode}
        GROUP BY st.store_id, st.code, st.name, st.city, st.manager_name
        ORDER BY total_revenue DESC;
    """
    df = pd.read_sql_query(query, conn, params=(start_date, REFERENCE_DATE))
    conn.close()

    result = []
    for _, row in df.iterrows():
        rev = float(row["total_revenue"])
        profit = float(row["total_profit"])
        margin = round((profit / rev * 100), 1) if rev > 0 else 0.0
        result.append({
            "store_id": int(row["store_id"]),
            "code": row["code"],
            "store_name": row["store_name"],
            "city": row["city"],
            "manager_name": row["manager_name"],
            "revenue": round(rev, 2),
            "profit": round(profit, 2),
            "total_revenue": round(rev, 2),
            "total_units": int(row["total_units"]),
            "total_profit": round(profit, 2),
            "profit_margin_pct": margin
        })
    return result

def get_category_performance(store_id: Optional[int] = None, days: int = 30, data_mode: str = "demo") -> List[Dict[str, Any]]:
    """Returns sales aggregation by category."""
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    start_date = (ref_dt - timedelta(days=days)).strftime("%Y-%m-%d")

    mode_clause = _build_mode_clause(data_mode, "s")
    store_clause = " AND s.store_id = ?" if store_id else ""
    params = [start_date, REFERENCE_DATE] + ([store_id] if store_id else [])

    query = f"""
        SELECT 
            c.category_id,
            c.name as category_name,
            COALESCE(SUM(s.revenue), 0) as total_revenue,
            COALESCE(SUM(s.units_sold), 0) as total_units,
            COALESCE(SUM(s.profit), 0) as total_profit
        FROM categories c
        JOIN products p ON c.category_id = p.category_id
        JOIN sales s ON p.product_id = s.product_id
        WHERE s.date >= ? AND s.date <= ? {store_clause} {mode_clause}
        GROUP BY c.category_id, c.name
        ORDER BY total_revenue DESC;
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df.to_dict(orient="records")

def detect_sales_anomalies(store_id: Optional[int] = None, data_mode: str = "demo") -> Dict[str, List[Dict[str, Any]]]:
    """
    Detects sales spikes and drops by comparing recent velocity (last 7 days)
    against historical baseline velocity (prior 30 days).
    """
    conn = get_connection()
    ref_dt = datetime.strptime(REFERENCE_DATE, "%Y-%m-%d")
    recent_start = (ref_dt - timedelta(days=RECENT_WINDOW_DAYS)).strftime("%Y-%m-%d")
    baseline_start = (ref_dt - timedelta(days=BASELINE_DAYS + RECENT_WINDOW_DAYS)).strftime("%Y-%m-%d")
    baseline_end = (ref_dt - timedelta(days=RECENT_WINDOW_DAYS + 1)).strftime("%Y-%m-%d")

    mode_clause = _build_mode_clause(data_mode, "s")
    store_clause = " AND s.store_id = ?" if store_id else ""
    params_base = [baseline_start, baseline_end] + ([store_id] if store_id else [])
    params_recent = [recent_start, REFERENCE_DATE] + ([store_id] if store_id else [])

    base_sql = f"""
        SELECT 
            s.store_id,
            st.name as store_name,
            s.product_id,
            p.name as product_name,
            p.sku,
            c.name as category_name,
            COALESCE(SUM(s.units_sold), 0) as base_units
        FROM sales s
        JOIN products p ON s.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        JOIN stores st ON s.store_id = st.store_id
        WHERE s.date >= ? AND s.date <= ? {store_clause} {mode_clause}
        GROUP BY s.store_id, st.name, s.product_id, p.name, p.sku, c.name;
    """
    base_df = pd.read_sql_query(base_sql, conn, params=params_base)

    recent_sql = f"""
        SELECT 
            s.store_id,
            s.product_id,
            COALESCE(SUM(s.units_sold), 0) as recent_units
        FROM sales s
        WHERE s.date >= ? AND s.date <= ? {store_clause} {mode_clause}
        GROUP BY s.store_id, s.product_id;
    """
    recent_df = pd.read_sql_query(recent_sql, conn, params=params_recent)
    conn.close()

    if base_df.empty or recent_df.empty:
        return {"spikes": [], "drops": []}

    merged = pd.merge(base_df, recent_df, on=["store_id", "product_id"], how="left")
    merged["recent_units"] = merged["recent_units"].fillna(0)

    merged["base_velocity"] = (merged["base_units"] / float(BASELINE_DAYS)).round(2)
    merged["recent_velocity"] = (merged["recent_units"] / float(RECENT_WINDOW_DAYS)).round(2)

    def calc_ratio(row):
        bv = row["base_velocity"]
        rv = row["recent_velocity"]
        if bv <= 0.1:
            return 1.0
        return round(rv / bv, 2)

    merged["velocity_ratio"] = merged.apply(calc_ratio, axis=1)
    merged["pct_change"] = ((merged["velocity_ratio"] - 1.0) * 100).round(1)

    spikes_df = merged[(merged["velocity_ratio"] >= SALES_SPIKE_RATIO) & (merged["recent_units"] >= 10)].sort_values(
        by="velocity_ratio", ascending=False
    )

    drops_df = merged[(merged["velocity_ratio"] <= SALES_DROP_RATIO) & (merged["base_velocity"] >= 1.0)].sort_values(
        by="velocity_ratio", ascending=True
    )

    return {
        "spikes": spikes_df.to_dict(orient="records"),
        "drops": drops_df.to_dict(orient="records")
    }
