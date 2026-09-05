"""
RetailIQ Copilot Service
Coordinates intent parsing, deterministic analytics, evidence generation,
and Gemini-grounded narrative explanation with Data Mode support.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from src.config import REFERENCE_DATE, BASELINE_DAYS, RECENT_WINDOW_DAYS, SAFETY_STOCK_BUFFER_DAYS
from src.models import CopilotResponse, EvidenceItem
from src.ai.gemini_client import extract_intent_with_gemini, generate_grounded_explanation
from src.ai.grounding import build_evidence_item, build_unsupported_response, format_evidence_markdown
from src.analytics.inventory import get_inventory_status, get_inventory_summary
from src.analytics.sales import (
    get_kpis, get_top_products, get_store_performance,
    detect_sales_anomalies
)
from src.analytics.recommendations import get_reorder_recommendations
from src.database import fetch_all, fetch_one
from src.utils.logging_config import logger

class CopilotService:
    @staticmethod
    def answer_query(
        query: str,
        store_id: Optional[int] = None,
        data_mode: str = "demo",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Main entry point for Store Manager natural-language questions."""
        logger.info(f"Processing Copilot query: '{query}' (Store filter: {store_id}, Mode: {data_mode})")

        # 1. Intent & Entity Extraction (Gemini / Deterministic fallback)
        intent_data = extract_intent_with_gemini(query)
        intent = intent_data["intent"]
        entities = intent_data.get("entities", {})

        # Contextual override: if store_id passed from header, use it
        active_store_id = store_id or entities.get("store_id")
        product_kw = entities.get("product")

        # Log audit trail
        try:
            from src.services.data_service import DataService
            DataService.log_audit(
                action="COPILOT_QUERY",
                details=f"Intent: {intent} | Mode: {data_mode} | Query: '{query}'",
                user_id=user_id
            )
        except Exception:
            pass

        # 2. Check for Unsupported Queries (Restraint / Guardrail)
        if intent == "unsupported_query":
            response = build_unsupported_response(query, reason=intent_data.get("unsupported_reason"))
            return response.to_dict()

        # 3. Deterministic Python Analytics Execution based on Intent
        evidence_items: List[EvidenceItem] = []
        details = []
        recommendations = []
        assumptions = []
        title = "RetailIQ Decision Intelligence"
        summary = ""

        # --- INTENT: STOCK OUT ---
        if intent == "stock_out":
            title = "Likely Stock-Out Risks"
            items = get_inventory_status(store_id=active_store_id, risk_filter="critical_stockout", data_mode=data_mode)
            if not items:
                items = get_inventory_status(store_id=active_store_id, risk_filter="low_stock", data_mode=data_mode)
            
            top_items = items[:5]
            for it in top_items:
                evidence_items.append(build_evidence_item(
                    metric=f"Estimated Runway ({it['product_name']})",
                    value=f"{it['days_remaining']} days ({it['current_stock']} units / {it['avg_daily_sales']} units/day)",
                    source_table="inventory, sales",
                    date_range=f"Previous {BASELINE_DAYS} days ending {REFERENCE_DATE}",
                    calculation="days_remaining = current_stock / avg_daily_sales",
                    assumptions=[
                        f"Demand continues at {it['avg_daily_sales']} units/day.",
                        f"Supplier lead time is {it.get('lead_time_days', 7)} days."
                    ]
                ))
                details.append({
                    "product_name": it["product_name"],
                    "store_name": it["store_name"],
                    "current_stock": it["current_stock"],
                    "avg_daily_sales": it["avg_daily_sales"],
                    "days_remaining": it["days_remaining"],
                    "estimated_stockout_date": it["estimated_stockout_date"],
                    "action": it["recommended_action"]
                })
                recommendations.append(f"Reorder {it['product_name']} at {it['store_name']}: {it['recommended_action']}")

            assumptions.append(f"Average daily sales calculated over the prior {BASELINE_DAYS} days.")
            assumptions.append(f"Stock-out flagged because runway ({top_items[0]['days_remaining'] if top_items else 0} days) is less than lead time + {SAFETY_STOCK_BUFFER_DAYS} safety buffer days.")

            if items:
                summary = (
                    f"Identified {len(items)} product(s) facing imminent stock-out risk. "
                    f"Most critical: **{top_items[0]['product_name']}** at {top_items[0]['store_name']} has only {top_items[0]['days_remaining']} days of stock remaining."
                )
            else:
                summary = f"No imminent stock-out risks detected under '{data_mode}' dataset. All product runways appear healthy."

        # --- INTENT: OVERSTOCK ---
        elif intent == "overstock":
            title = "Overstocked Inventory Analysis"
            items = get_inventory_status(store_id=active_store_id, risk_filter="overstocked", data_mode=data_mode)
            top_items = items[:5]
            for it in top_items:
                evidence_items.append(build_evidence_item(
                    metric=f"Days of Supply ({it['product_name']})",
                    value=f"{it['days_remaining']} days ({it['current_stock']} units in stock)",
                    source_table="inventory, sales",
                    date_range=f"Previous {BASELINE_DAYS} days ending {REFERENCE_DATE}",
                    calculation="days_of_inventory = current_stock / avg_daily_sales",
                    assumptions=[
                        f"Normal healthy inventory turnover target is under 60 days.",
                        f"Capital tied up: ₹{it['stock_value']:,.2f}."
                    ]
                ))
                details.append({
                    "product_name": it["product_name"],
                    "store_name": it["store_name"],
                    "current_stock": it["current_stock"],
                    "avg_daily_sales": it["avg_daily_sales"],
                    "days_remaining": it["days_remaining"],
                    "tied_up_capital": f"₹{it['stock_value']:,.2f}",
                    "action": it["recommended_action"]
                })
                recommendations.append(f"{it['product_name']} at {it['store_name']}: {it['recommended_action']}")

            assumptions.append("Overstock condition triggered when days of inventory exceed 60 days and stock count > 50 units.")
            if items:
                summary = (
                    f"Detected {len(items)} overstocked SKU(s). "
                    f"Notable surplus: **{top_items[0]['product_name']}** at {top_items[0]['store_name']} holds {top_items[0]['current_stock']} units ({top_items[0]['days_remaining']} days of supply)."
                )
            else:
                summary = f"No overstocked items detected in '{data_mode}' mode."

        # --- INTENT: SLOW MOVING ---
        elif intent == "slow_moving":
            title = "Slow-Moving Product Identification"
            items = get_inventory_status(store_id=active_store_id, risk_filter="slow_moving", data_mode=data_mode)
            top_items = items[:5]
            for it in top_items:
                evidence_items.append(build_evidence_item(
                    metric=f"Sales Velocity ({it['product_name']})",
                    value=f"{it['avg_daily_sales']} units/day",
                    source_table="sales, inventory",
                    date_range=f"Previous {BASELINE_DAYS} days ending {REFERENCE_DATE}",
                    calculation="avg_daily_sales = total_units_sold / 30",
                    assumptions=["Velocity threshold for slow-moving classification is <0.25 units/day."]
                ))
                details.append({
                    "product_name": it["product_name"],
                    "store_name": it["store_name"],
                    "current_stock": it["current_stock"],
                    "avg_daily_sales": it["avg_daily_sales"],
                    "days_remaining": it["days_remaining"],
                    "action": it["recommended_action"]
                })
                recommendations.append(f"Promote or bundle {it['product_name']} at {it['store_name']}.")

            assumptions.append("Slow-moving products have daily velocity under 0.25 units/day over 30 days.")
            if items:
                summary = (
                    f"Found {len(items)} slow-moving product(s). "
                    f"Example: **{top_items[0]['product_name']}** at {top_items[0]['store_name']} is selling at only {top_items[0]['avg_daily_sales']} units/day."
                )
            else:
                summary = f"No slow-moving inventory detected in '{data_mode}' mode."

        # --- INTENT: SALES SPIKE ---
        elif intent == "sales_spike":
            title = "Unusual Sales Spikes Detected"
            anomalies = detect_sales_anomalies(store_id=active_store_id, data_mode=data_mode)
            spikes = anomalies.get("spikes", [])[:5]
            for sp in spikes:
                evidence_items.append(build_evidence_item(
                    metric=f"Velocity Surge ({sp['product_name']})",
                    value=f"+{sp['pct_change']}% surge ({sp['recent_velocity']} units/day vs {sp['base_velocity']} baseline)",
                    source_table="sales",
                    date_range=f"Recent 7 days vs prior {BASELINE_DAYS} days",
                    calculation="velocity_ratio = recent_7d_velocity / baseline_30d_velocity",
                    assumptions=["Sales spike threshold is defined as a recent velocity ratio >= 1.50x with >=10 units sold."]
                ))
                details.append({
                    "product_name": sp["product_name"],
                    "store_name": sp["store_name"],
                    "recent_velocity": f"{sp['recent_velocity']} units/day",
                    "baseline_velocity": f"{sp['base_velocity']} units/day",
                    "increase": f"+{sp['pct_change']}%",
                    "action": "Ensure inventory replenishment order is adjusted upward to prevent stock-out."
                })
                recommendations.append(f"Audit stock buffer for {sp['product_name']} at {sp['store_name']} to meet sustained elevated demand.")

            assumptions.append(f"Recent velocity measured over the last {RECENT_WINDOW_DAYS} days; baseline measured over prior {BASELINE_DAYS} days.")
            if spikes:
                summary = (
                    f"Detected {len(spikes)} notable sales surge(s). "
                    f"Top spike: **{spikes[0]['product_name']}** at {spikes[0]['store_name']} jumped by **+{spikes[0]['pct_change']}%** to {spikes[0]['recent_velocity']} units/day."
                )
            else:
                summary = f"No unusual sales spikes (>= 1.50x baseline) detected in '{data_mode}' mode."

        # --- INTENT: SALES DROP ---
        elif intent == "sales_drop":
            title = "Sales Drop & Demand Slump Analysis"
            anomalies = detect_sales_anomalies(store_id=active_store_id, data_mode=data_mode)
            drops = anomalies.get("drops", [])[:5]
            for dr in drops:
                evidence_items.append(build_evidence_item(
                    metric=f"Velocity Decline ({dr['product_name']})",
                    value=f"-{abs(dr['pct_change'])}% drop ({dr['recent_velocity']} units/day vs {dr['base_velocity']} baseline)",
                    source_table="sales",
                    date_range=f"Recent 7 days vs prior {BASELINE_DAYS} days",
                    calculation="velocity_ratio = recent_7d_velocity / baseline_30d_velocity",
                    assumptions=["Sales drop flagged when recent velocity <= 0.60x of historical baseline."]
                ))
                details.append({
                    "product_name": dr["product_name"],
                    "store_name": dr["store_name"],
                    "recent_velocity": f"{dr['recent_velocity']} units/day",
                    "baseline_velocity": f"{dr['base_velocity']} units/day",
                    "decrease": f"-{abs(dr['pct_change'])}%",
                    "action": "Inspect shelf visibility, check competitor pricing, and verify product expiration or batch issues."
                })
                recommendations.append(f"Investigate demand decline for {dr['product_name']} at {dr['store_name']}.")

            assumptions.append(f"Drop threshold triggered at <= 60% of {BASELINE_DAYS}-day baseline volume.")
            if drops:
                summary = (
                    f"Detected {len(drops)} product(s) suffering significant sales slumps. "
                    f"Largest drop: **{drops[0]['product_name']}** at {drops[0]['store_name']} declined by **-{abs(drops[0]['pct_change'])}%** to {drops[0]['recent_velocity']} units/day."
                )
            else:
                summary = f"No significant sales drops (<= 0.60x baseline) detected in '{data_mode}' mode."

        # --- INTENT: REORDER RECOMMENDATION ---
        elif intent == "reorder_recommendation":
            title = "Recommended Replenishment Orders"
            reorders = get_reorder_recommendations(store_id=active_store_id, data_mode=data_mode)[:5]
            for ro in reorders:
                evidence_items.append(build_evidence_item(
                    metric=f"Reorder Quantity ({ro['product_name']} @ {ro['store_name']})",
                    value=f"{ro['recommended_reorder_qty']} units (Est. ₹{ro['estimated_investment']:,.2f})",
                    source_table="inventory, products, sales",
                    date_range=f"Forecast based on 30-day demand velocity ({ro['avg_daily_sales']} units/day)",
                    calculation="reorder_qty = max(min_reorder, round((lead_time + 21) * avg_sales + safety_stock - current_stock))",
                    assumptions=ro["assumptions"]
                ))
                details.append({
                    "product_name": ro["product_name"],
                    "store_name": ro["store_name"],
                    "current_stock": ro["current_stock"],
                    "lead_time_days": ro["lead_time_days"],
                    "recommended_reorder_qty": ro["recommended_reorder_qty"],
                    "urgency": ro["urgency"],
                    "estimated_investment": f"₹{ro['estimated_investment']:,.2f}"
                })
                recommendations.append(f"Create draft replenishment order for {ro['recommended_reorder_qty']} units of {ro['product_name']} ({ro['store_name']}) for human review.")

            assumptions.append("Reorder quantities calculated to cover supplier lead time plus a 21-day target replenishment cycle.")
            if reorders:
                summary = (
                    f"Formulated {len(reorders)} replenishment recommendations based on lead times and demand. "
                    f"Primary priority: **{reorders[0]['product_name']}** requires {reorders[0]['recommended_reorder_qty']} units."
                )
            else:
                summary = f"No replenishment orders required at this time in '{data_mode}' mode."

        # --- INTENT: STORE PERFORMANCE ---
        elif intent == "store_performance":
            title = "Store Performance Comparison"
            stores = get_store_performance(days=30, data_mode=data_mode)
            best_store = stores[0] if stores else None
            for st in stores:
                evidence_items.append(build_evidence_item(
                    metric=f"Revenue - {st['store_name']}",
                    value=f"₹{st['total_revenue']:,.2f} ({st['total_units']:,} units, margin: {st['profit_margin_pct']}%)",
                    source_table="sales, stores",
                    date_range=f"Last 30 days ending {REFERENCE_DATE}",
                    calculation="SUM(revenue), SUM(units_sold) grouped by store_id"
                ))
                details.append({
                    "store_name": st["store_name"],
                    "city": st["city"],
                    "manager": st["manager_name"],
                    "revenue": f"₹{st['total_revenue']:,.2f}",
                    "units_sold": f"{st['total_units']:,}",
                    "profit_margin": f"{st['profit_margin_pct']}%"
                })

            if best_store:
                summary = (
                    f"**{best_store['store_name']}** is the leading store with **₹{best_store['total_revenue']:,.2f}** in revenue "
                    f"({best_store['total_units']:,} units sold, {best_store['profit_margin_pct']}% margin). "
                    f"Managed by {best_store['manager_name']}."
                )
                recommendations.append(f"Benchmark store practices from {best_store['store_name']} across other locations.")
            else:
                summary = f"No store sales transactions recorded in '{data_mode}' mode."
            assumptions.append(f"Store ranking evaluated by total revenue over the last 30 days ending {REFERENCE_DATE}.")

        # --- INTENT: PRODUCT PERFORMANCE ---
        elif intent == "product_performance":
            title = "Product Performance Deep Dive"
            matched_prod = None
            mode_filter = " AND is_demo = 1" if data_mode == "demo" else " AND is_demo = 0" if data_mode == "user" else ""
            if product_kw:
                prods = fetch_all(f"SELECT * FROM products WHERE LOWER(name) LIKE ? {mode_filter} LIMIT 1", (f"%{product_kw}%",))
                if prods:
                    matched_prod = prods[0]

            if not matched_prod:
                prods = fetch_all(f"SELECT * FROM products WHERE 1=1 {mode_filter} LIMIT 1")
                if prods:
                    matched_prod = prods[0]

            if matched_prod:
                pid = matched_prod["product_id"]
                pname = matched_prod["name"]

                perf_rows = fetch_all("""
                    SELECT 
                        s.store_id, st.name as store_name,
                        SUM(s.units_sold) as total_units,
                        ROUND(SUM(s.revenue), 2) as total_revenue,
                        ROUND(SUM(s.profit), 2) as total_profit,
                        ROUND(AVG(s.units_sold), 2) as avg_velocity,
                        i.current_stock, i.safety_stock, i.lead_time_days
                    FROM products p
                    JOIN sales s ON p.product_id = s.product_id
                    JOIN stores st ON s.store_id = st.store_id
                    JOIN inventory i ON s.store_id = i.store_id AND s.product_id = i.product_id
                    WHERE p.product_id = ? AND s.date >= date(?, '-30 days') AND s.date <= ?
                    GROUP BY s.store_id, st.name;
                """, (pid, REFERENCE_DATE, REFERENCE_DATE))

                total_u = sum(r["total_units"] for r in perf_rows)
                total_r = sum(r["total_revenue"] for r in perf_rows)

                evidence_items.append(build_evidence_item(
                    metric=f"30-Day Sales Volume ({pname})",
                    value=f"{total_u} units across stores (₹{total_r:,.2f} revenue)",
                    source_table="sales",
                    date_range=f"Last 30 days ending {REFERENCE_DATE}",
                    calculation="SUM(units_sold), SUM(revenue) WHERE product_id = ?"
                ))

                for r in perf_rows:
                    days_rem = round(r["current_stock"] / (r["avg_velocity"] if r["avg_velocity"] > 0 else 1), 1)
                    details.append({
                        "store_name": r["store_name"],
                        "units_sold": r["total_units"],
                        "revenue": f"₹{r['total_revenue']:,.2f}",
                        "avg_velocity": f"{r['avg_velocity']} units/day",
                        "current_stock": r["current_stock"],
                        "days_remaining": days_rem
                    })
                    if days_rem <= ((r.get("lead_time_days") or 7) + 2):
                        recommendations.append(f"Create draft reorder for {pname} at {r['store_name']} ({days_rem} days remaining).")

                summary = f"**{pname}** generated **₹{total_r:,.2f}** ({total_u} units sold) in the reporting period."
                assumptions.append(f"Figures based on sales transactions between {REFERENCE_DATE} and 30 days prior.")
            else:
                summary = f"No matching product data found in '{data_mode}' mode."

        # --- INTENT: SALES PERFORMANCE / TOP PRODUCTS / DEFAULT ---
        elif intent in ("sales_performance", "top_products", "general_data_question"):
            title = "Sales & Operations Overview"
            kpis = get_kpis(store_id=active_store_id, days=30, data_mode=data_mode)
            top_prods = get_top_products(store_id=active_store_id, limit=5, days=30, data_mode=data_mode)

            evidence_items.append(build_evidence_item(
                metric="Total Revenue (30 Days)",
                value=f"₹{kpis['total_revenue']:,.2f} (Growth: {kpis['revenue_growth_pct']:+}%)",
                source_table="sales",
                date_range=kpis["date_range"],
                calculation="SUM(revenue) across filtered stores"
            ))
            evidence_items.append(build_evidence_item(
                metric="Units Sold (30 Days)",
                value=f"{kpis['total_units']:,} units (Margin: {kpis['profit_margin_pct']}%)",
                source_table="sales",
                date_range=kpis["date_range"],
                calculation="SUM(units_sold), (profit / revenue) * 100"
            ))

            for tp in top_prods:
                details.append({
                    "product_name": tp["product_name"],
                    "category": tp["category_name"],
                    "units_sold": tp["total_units"],
                    "revenue": f"₹{tp['total_revenue']:,.2f}"
                })

            if kpis["total_revenue"] > 0:
                summary = (
                    f"Total operations revenue reached **₹{kpis['total_revenue']:,.2f}** "
                    f"across **{kpis['total_units']:,}** units with a **{kpis['profit_margin_pct']}%** margin. "
                    + (f"Top seller: **{top_prods[0]['product_name']}** (₹{top_prods[0]['total_revenue']:,.2f})." if top_prods else "")
                )
            else:
                summary = f"No sales records found in '{data_mode}' mode. You can record daily transactions via the Data Management tab."
            recommendations.append("Continue monitoring category demand trajectories.")
            assumptions.append(f"Aggregations calculated over the 30-day reporting window ending {REFERENCE_DATE}.")

        # --- INTENT: INVENTORY SUMMARY ---
        elif intent in ("inventory_summary", "low_stock"):
            title = "Overall Inventory Health Status"
            summary_data = get_inventory_summary(store_id=active_store_id, data_mode=data_mode)
            evidence_items.append(build_evidence_item(
                metric="Total Inventory Valuation",
                value=f"₹{summary_data['total_cost_value']:,.2f} cost (₹{summary_data['total_retail_value']:,.2f} retail)",
                source_table="inventory, products",
                date_range=f"Current snapshot as of {REFERENCE_DATE}",
                calculation="SUM(current_stock * cost_price)"
            ))
            evidence_items.append(build_evidence_item(
                metric="Stockout & Risk Counts",
                value=f"{summary_data['critical_stockouts']} Critical, {summary_data['low_stock_items']} Low Stock, {summary_data['overstocked_items']} Overstocked",
                source_table="inventory, sales",
                date_range=f"Evaluated against {BASELINE_DAYS}-day velocity",
                calculation="Categorized by days_remaining vs lead_time rules"
            ))

            details.append({
                "total_stock_units": f"{summary_data['total_stock_units']:,}",
                "critical_stockouts": summary_data["critical_stockouts"],
                "overstocked_items": summary_data["overstocked_items"],
                "slow_moving_items": summary_data["slow_moving_items"],
                "healthy_items": summary_data["healthy_items"]
            })

            summary = (
                f"Total inventory comprises **{summary_data['total_stock_units']:,} units** valued at **₹{summary_data['total_cost_value']:,.2f}**. "
                f"Currently tracking **{summary_data['critical_stockouts']} critical stock-outs** and **{summary_data['overstocked_items']} overstocked SKUs** in '{data_mode}' mode."
            )
            recommendations.append("Review draft reorders for critical items and check turnover for overstocked items.")
            assumptions.append("All inventory statuses derived from verified database records.")

        # 4. Synthesize narrative using Gemini if available, else deterministic template
        evidence_text = format_evidence_markdown(evidence_items)
        data_text = f"Summary: {summary}\nDetails: {details}\nRecommendations: {recommendations}\nAssumptions: {assumptions}"

        gemini_narrative = generate_grounded_explanation(
            query=query,
            intent=intent,
            evidence_context=evidence_text,
            data_context=data_text
        )

        model_used = "gemini-flash" if gemini_narrative else "deterministic_verified"
        final_summary = gemini_narrative if gemini_narrative else summary

        return CopilotResponse(
            query=query,
            intent=intent,
            title=title,
            summary=final_summary,
            details=details,
            evidence=evidence_items,
            recommendations=recommendations,
            assumptions=assumptions,
            data_limitations=None,
            is_grounded=True,
            model_used=model_used
        ).to_dict()
