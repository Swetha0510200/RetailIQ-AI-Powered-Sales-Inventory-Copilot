"""
RetailIQ Dashboard & UI Service
Aggregates and formats data for all application pages, supporting Demo vs User data modes.
"""

from typing import Dict, Any, List, Optional
from src.analytics.inventory import get_inventory_status, get_inventory_summary
from src.analytics.sales import (
    get_kpis, get_sales_trends, get_top_products,
    get_store_performance, get_category_performance
)
from src.analytics.alerts import generate_alerts
from src.database import fetch_all, fetch_one
from src.config import REFERENCE_DATE

class DashboardService:
    @staticmethod
    def get_dashboard_overview(store_id: Optional[int] = None, data_mode: str = "demo") -> Dict[str, Any]:
        """Returns consolidated data for Page 1: Dashboard."""
        kpis = get_kpis(store_id=store_id, days=30, data_mode=data_mode)
        trends = get_sales_trends(store_id=store_id, days=30, data_mode=data_mode)
        top_prods = get_top_products(store_id=store_id, limit=5, days=30, data_mode=data_mode)
        stores_perf = get_store_performance(days=30, data_mode=data_mode)
        inv_summary = get_inventory_summary(store_id=store_id, data_mode=data_mode)
        all_alerts = generate_alerts(store_id=store_id, data_mode=data_mode)

        return {
            "data_mode": data_mode,
            "kpis": kpis,
            "sales_trends": trends,
            "top_products": top_prods,
            "store_performance": stores_perf,
            "inventory_summary": inv_summary,
            "recent_alerts": all_alerts[:5],
            "total_alerts_count": len(all_alerts)
        }

    @staticmethod
    def get_inventory_page_data(
        store_id: Optional[int] = None,
        category_id: Optional[int] = None,
        risk_filter: Optional[str] = None,
        search: Optional[str] = None,
        data_mode: str = "demo"
    ) -> Dict[str, Any]:
        """Returns data for Page 3: Inventory."""
        items = get_inventory_status(
            store_id=store_id, category_id=category_id, risk_filter=risk_filter, data_mode=data_mode
        )
        if search:
            s = search.lower()
            items = [
                it for it in items
                if s in it["product_name"].lower() or s in it["sku"].lower() or s in it.get("supplier_name", "").lower()
            ]

        summary = get_inventory_summary(store_id=store_id, data_mode=data_mode)
        
        mode_store_clause = "WHERE is_demo = 1" if data_mode == "demo" else "WHERE is_demo = 0" if data_mode == "user" else ""
        stores = fetch_all(f"SELECT store_id, name, city FROM stores {mode_store_clause} ORDER BY store_id ASC;")
        categories = fetch_all("SELECT category_id, name FROM categories ORDER BY category_id ASC;")

        return {
            "data_mode": data_mode,
            "items": items,
            "total_count": len(items),
            "summary": summary,
            "stores": stores,
            "categories": categories
        }

    @staticmethod
    def get_sales_page_data(store_id: Optional[int] = None, days: int = 30, data_mode: str = "demo") -> Dict[str, Any]:
        """Returns data for Page 4: Sales Analytics."""
        kpis = get_kpis(store_id=store_id, days=days, data_mode=data_mode)
        trends = get_sales_trends(store_id=store_id, days=days, data_mode=data_mode)
        cat_perf = get_category_performance(store_id=store_id, days=days, data_mode=data_mode)
        top_rev = get_top_products(store_id=store_id, limit=8, days=days, by="revenue", data_mode=data_mode)
        top_units = get_top_products(store_id=store_id, limit=8, days=days, by="units", data_mode=data_mode)
        
        mode_store_clause = "WHERE is_demo = 1" if data_mode == "demo" else "WHERE is_demo = 0" if data_mode == "user" else ""
        stores = fetch_all(f"SELECT store_id, name, city FROM stores {mode_store_clause} ORDER BY store_id ASC;")

        return {
            "data_mode": data_mode,
            "kpis": kpis,
            "trends": trends,
            "category_performance": cat_perf,
            "top_by_revenue": top_rev,
            "top_by_units": top_units,
            "stores": stores
        }

    @staticmethod
    def get_alerts_page_data(store_id: Optional[int] = None, data_mode: str = "demo") -> Dict[str, Any]:
        """Returns data for Page 5: Alerts."""
        alerts = generate_alerts(store_id=store_id, data_mode=data_mode)
        counts = {
            "total": len(alerts),
            "critical": sum(1 for a in alerts if a["severity"] == "critical"),
            "warning": sum(1 for a in alerts if a["severity"] == "warning"),
            "info": sum(1 for a in alerts if a["severity"] == "info")
        }
        return {
            "data_mode": data_mode,
            "alerts": alerts,
            "counts": counts
        }

    @staticmethod
    def get_products_page_data(
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        data_mode: str = "demo"
    ) -> Dict[str, Any]:
        """Returns data for Page 6: Products Catalogue."""
        query = """
            SELECT 
                p.product_id, p.sku, p.name, p.category_id, c.name as category_name,
                p.cost_price, p.selling_price,
                ROUND((p.selling_price - p.cost_price), 2) as margin_amount,
                ROUND(((p.selling_price - p.cost_price) / p.selling_price * 100), 1) as margin_pct,
                p.supplier_name, p.lead_time_days, p.min_reorder_qty,
                COALESCE(SUM(i.current_stock), 0) as total_network_stock
            FROM products p
            JOIN categories c ON p.category_id = c.category_id
            LEFT JOIN inventory i ON p.product_id = i.product_id
        """
        conditions = []
        params = []
        if data_mode == "demo":
            conditions.append("p.is_demo = 1")
        elif data_mode == "user":
            conditions.append("p.is_demo = 0")

        if category_id:
            conditions.append("p.category_id = ?")
            params.append(category_id)
        if search:
            conditions.append("(LOWER(p.name) LIKE ? OR LOWER(p.sku) LIKE ? OR LOWER(p.supplier_name) LIKE ?)")
            term = f"%{search.lower()}%"
            params.extend([term, term, term])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " GROUP BY p.product_id, p.sku, p.name, p.category_id, c.name ORDER BY p.product_id ASC;"
        prods = fetch_all(query, tuple(params) if params else ())
        categories = fetch_all("SELECT category_id, name FROM categories ORDER BY category_id ASC;")

        return {
            "data_mode": data_mode,
            "products": prods,
            "total_count": len(prods),
            "categories": categories
        }

    @staticmethod
    def get_stores_page_data(data_mode: str = "demo") -> Dict[str, Any]:
        """Returns data for Page 7: Stores."""
        stores_perf = get_store_performance(days=30, data_mode=data_mode)
        
        for st in stores_perf:
            sid = st["store_id"]
            inv_sum = get_inventory_summary(store_id=sid, data_mode=data_mode)
            st["stock_units"] = inv_sum["total_stock_units"]
            st["inventory_value"] = inv_sum["total_cost_value"]
            st["critical_stockouts"] = inv_sum["critical_stockouts"]
            st["overstocked_items"] = inv_sum["overstocked_items"]

        return {
            "data_mode": data_mode,
            "stores": stores_perf
        }

    @staticmethod
    def get_data_explorer_data(
        table_name: str = "inventory",
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        data_mode: str = "all"
    ) -> Dict[str, Any]:
        """Returns raw database table records for Page 8: Data Explorer and audit."""
        allowed_tables = {
            "stores", "categories", "products", "inventory",
            "sales", "reorder_requests", "audit_logs"
        }
        if table_name not in allowed_tables:
            table_name = "inventory"

        # Count total
        count_row = fetch_one(f"SELECT COUNT(*) as total FROM {table_name};")
        total_rows = count_row["total"] if count_row else 0

        # Fetch records
        query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT ? OFFSET ?;"
        rows = fetch_all(query, (limit, offset))

        columns = list(rows[0].keys()) if rows else []

        return {
            "table_name": table_name,
            "available_tables": list(allowed_tables),
            "columns": columns,
            "rows": rows,
            "total_rows": total_rows,
            "limit": limit,
            "offset": offset
        }

    @staticmethod
    def get_recommendations_page_data(store_id: Optional[int] = None, data_mode: str = "demo") -> Dict[str, Any]:
        """Returns structured data for Page: Reorder Recommendations."""
        from src.analytics.recommendations import get_reorder_recommendations
        recs = get_reorder_recommendations(store_id=store_id, data_mode=data_mode)
        total_inv = sum(r.get("estimated_investment", 0) for r in recs)
        total_units = sum(r.get("recommended_reorder_qty", 0) for r in recs)
        urgent_count = sum(1 for r in recs if r.get("urgency") == "Urgent")

        mode_store_clause = "WHERE is_demo = 1" if data_mode == "demo" else "WHERE is_demo = 0" if data_mode == "user" else ""
        stores = fetch_all(f"SELECT store_id, name, city FROM stores {mode_store_clause} ORDER BY store_id ASC;")

        return {
            "data_mode": data_mode,
            "recommendations": recs,
            "total_items": len(recs),
            "urgent_count": urgent_count,
            "total_units_recommended": total_units,
            "total_investment_estimated": round(total_inv, 2),
            "stores": stores
        }
