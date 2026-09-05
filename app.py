"""
RetailIQ — AI-Powered Sales & Inventory Copilot
Track ID: PS03 (NexusTiQ24)
Single-file server entrypoint.

Run via:
    python app.py
Accessible at:
    http://localhost:8000
"""

import os
import sys
from functools import wraps
from datetime import datetime
from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, flash
)

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import (
    APP_NAME, APP_TITLE, TRACK_ID, TAGLINE, VERSION,
    HOST, PORT, DEBUG, SECRET_KEY, GEMINI_API_KEY, GEMINI_MODEL,
    REFERENCE_DATE, DATABASE_PATH, DATA_MODE_DEMO, DATA_MODE_USER, DATA_MODE_ALL
)
from src.utils.logging_config import logger
from src.database import init_db, fetch_all, fetch_one
from src.seed_data import seed_database
from src.services.auth_service import AuthService
from src.services.data_service import DataService
from src.services.copilot_service import CopilotService
from src.services.dashboard_service import DashboardService

# Initialize Flask Application
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)
app.secret_key = SECRET_KEY

# --------------------------------------------------------------------------
# Startup & Database Verification
# --------------------------------------------------------------------------
@app.before_request
def ensure_initialized():
    """Ensures database is initialized, migrated, and seeded before first request."""
    if not hasattr(app, "_db_ready"):
        init_db()
        seed_database(force=False)
        AuthService.ensure_demo_user()
        app._db_ready = True

def login_required(f):
    """Decorator to enforce authentication on protected pages and APIs."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Authentication required."}), 401
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Helper to fetch currently authenticated user object from session."""
    if "user_id" in session:
        return AuthService.get_user_by_id(session["user_id"])
    return None

# --------------------------------------------------------------------------
# Root & Authentication Routes
# --------------------------------------------------------------------------
@app.route("/")
def root():
    """Root route: redirects to /dashboard if authenticated, else /login."""
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
def login_page():
    """Serves the standalone Login page and handles credential verification."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        res = AuthService.authenticate_user(email=email, password=password, ip_address=request.remote_addr)
        if res["success"]:
            user = res["user"]
            session["user_id"] = user["user_id"]
            session["user_email"] = user["email"]
            session["user_name"] = user["full_name"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard_page"))
        else:
            flash(res.get("error", "Invalid email or password."), "error")
            return render_template("login.html", default_email=email)

    # GET request
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return render_template("login.html", default_email="manager@retailiq.internal")

@app.route("/register", methods=["GET", "POST"])
def register_page():
    """Serves the standalone Registration page and handles new user creation."""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        business_name = request.form.get("business_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        res = AuthService.register_user(
            full_name=full_name,
            email=email,
            password=password,
            confirm_password=confirm_password,
            business_name=business_name,
            ip_address=request.remote_addr
        )

        if res["success"]:
            flash("Account registered successfully! Please log in with your credentials.", "success")
            return redirect(url_for("login_page"))
        else:
            flash(res.get("error", "Registration failed."), "error")
            return render_template("register.html")

    # GET request
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return render_template("register.html")

@app.route("/logout", methods=["GET", "POST"])
def logout():
    """Logs out the current user, clears session, and redirects to /login."""
    user_id = session.get("user_id")
    user_email = session.get("user_email")
    session.clear()

    if user_id:
        DataService.log_audit(
            action="USER_LOGOUT",
            details="User logged out",
            user_id=user_id,
            user_email=user_email,
            ip_address=request.remote_addr
        )

    flash("You have been signed out.", "info")
    return redirect(url_for("login_page"))

# --------------------------------------------------------------------------
# Protected Application Pages
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard_page():
    """Page 1: Executive Dashboard with KPIs, 4 Chart.js charts, and alerts."""
    store_id = request.args.get("store_id", type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)
    
    overview = DashboardService.get_dashboard_overview(store_id=store_id, data_mode=data_mode)
    stores_count = fetch_one("SELECT COUNT(*) as c FROM stores;")["c"]
    total_products_count = fetch_one("SELECT COUNT(*) as c FROM products;")["c"]

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        page_heading="Executive Retail Dashboard",
        page_subheading="Autonomous Decision Intelligence & Operations",
        current_user=get_current_user(),
        current_mode=data_mode,
        kpis=overview["kpis"],
        sales_trends=overview["sales_trends"],
        store_performance=overview["store_performance"],
        inventory_summary=overview["inventory_summary"],
        recent_alerts=overview["recent_alerts"],
        total_alerts_count=overview["total_alerts_count"],
        stores_count=stores_count,
        total_products_count=total_products_count
    )

@app.route("/copilot")
@login_required
def copilot_page():
    """Page 2: AI Copilot conversational natural language decision assistant."""
    data_mode = request.args.get("data_mode", default="demo", type=str)
    return render_template(
        "copilot.html",
        active_page="copilot",
        page_heading="AI Copilot",
        page_subheading="Grounded Conversational Intelligence",
        current_user=get_current_user(),
        current_mode=data_mode
    )

@app.route("/inventory")
@login_required
def inventory_page():
    """Page 3: Comprehensive Inventory Management and Stock Runway."""
    store_id = request.args.get("store_id", type=int)
    category_id = request.args.get("category_id", type=int)
    risk_filter = request.args.get("risk_filter", type=str)
    search = request.args.get("search", type=str)
    data_mode = request.args.get("data_mode", default="demo", type=str)

    data = DashboardService.get_inventory_page_data(
        store_id=store_id,
        category_id=category_id,
        risk_filter=risk_filter,
        search=search,
        data_mode=data_mode
    )
    all_products = fetch_all("SELECT product_id, sku, name FROM products ORDER BY name ASC;")

    return render_template(
        "inventory.html",
        active_page="inventory",
        page_heading="Inventory & Stock Health",
        page_subheading="Real-Time Runways & Replenishment Signals",
        current_user=get_current_user(),
        current_mode=data_mode,
        items=data["items"],
        summary=data["summary"],
        stores=data["stores"],
        categories=data["categories"],
        selected_store=store_id,
        selected_category=category_id,
        selected_risk=risk_filter,
        search=search,
        all_products=all_products,
        reference_date=REFERENCE_DATE
    )

@app.route("/products")
@login_required
def products_page():
    """Page 4: Product Master Catalog & Unit Economics."""
    category_id = request.args.get("category_id", type=int)
    search = request.args.get("search", type=str)
    data_mode = request.args.get("data_mode", default="demo", type=str)

    data = DashboardService.get_products_page_data(
        category_id=category_id,
        search=search,
        data_mode=data_mode
    )

    return render_template(
        "products.html",
        active_page="products",
        page_heading="Product Master Catalog",
        page_subheading="Central SKU Directory, Unit Costs & Lead Times",
        current_user=get_current_user(),
        current_mode=data_mode,
        products=data["products"],
        categories=data["categories"],
        selected_category=category_id,
        search=search
    )

@app.route("/stores")
@login_required
def stores_page():
    """Page 5: Retail Stores Directory and Footprint Performance."""
    data_mode = request.args.get("data_mode", default="demo", type=str)
    data = DashboardService.get_stores_page_data(data_mode=data_mode)

    return render_template(
        "stores.html",
        active_page="stores",
        page_heading="Retail Stores Directory",
        page_subheading="Store Locations, Local Inventory & Manager Contacts",
        current_user=get_current_user(),
        current_mode=data_mode,
        stores=data["stores"]
    )

@app.route("/sales")
@login_required
def sales_page():
    """Page 6: Sales Operations, POS Logging, and Demand Velocity."""
    store_id = request.args.get("store_id", type=int)
    days = request.args.get("days", default=30, type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)

    data = DashboardService.get_sales_page_data(store_id=store_id, days=days, data_mode=data_mode)
    
    # Fetch recent 50 sales
    store_filter = "WHERE s.store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    recent_sales = fetch_all(f"""
        SELECT s.sale_id, s.date, st.name as store_name, p.name as product_name, p.sku, s.units_sold, s.unit_price, s.revenue, s.profit
        FROM sales s
        JOIN stores st ON s.store_id = st.store_id
        JOIN products p ON s.product_id = p.product_id
        {store_filter}
        ORDER BY s.date DESC, s.sale_id DESC
        LIMIT 50;
    """, params)

    all_products = fetch_all("SELECT product_id, sku, name, selling_price FROM products ORDER BY name ASC;")

    return render_template(
        "sales.html",
        active_page="sales",
        page_heading="Sales Operations & Demand",
        page_subheading="Transaction Registers, POS Entry & Margin Analysis",
        current_user=get_current_user(),
        current_mode=data_mode,
        kpis=data["kpis"],
        stores=data["stores"],
        selected_store=store_id,
        period_days=days,
        recent_sales=recent_sales,
        all_products=all_products,
        reference_date=REFERENCE_DATE
    )

@app.route("/alerts")
@login_required
def alerts_page():
    """Page 7: Operational Alerts & Exception Management."""
    store_id = request.args.get("store_id", type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)
    severity = request.args.get("severity", type=str)
    alert_type = request.args.get("alert_type", type=str)

    data = DashboardService.get_alerts_page_data(store_id=store_id, data_mode=data_mode)
    alerts = data["alerts"]
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]
    if alert_type:
        alerts = [a for a in alerts if a["alert_type"] == alert_type]

    stores = fetch_all("SELECT store_id, name FROM stores ORDER BY store_id ASC;")

    return render_template(
        "alerts.html",
        active_page="alerts",
        page_heading="Prioritized Operational Alerts",
        page_subheading="Automated Exception Engine with Grounded Audit Lineage",
        current_user=get_current_user(),
        current_mode=data_mode,
        alerts=alerts,
        counts=data["counts"],
        stores=stores,
        selected_store=store_id,
        selected_severity=severity,
        selected_type=alert_type
    )

@app.route("/recommendations")
@login_required
def recommendations_page():
    """Page 8: Deterministic Replenishment Recommendations & Draft Orders."""
    store_id = request.args.get("store_id", type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)

    data = DashboardService.get_recommendations_page_data(store_id=store_id, data_mode=data_mode)
    draft_requests = DataService.get_reorder_requests(limit=50, data_mode=data_mode)

    return render_template(
        "recommendations.html",
        active_page="recommendations",
        page_heading="Replenishment Recommendations",
        page_subheading="Deterministic Reorder Quantities with Human-in-the-Loop Signoff",
        current_user=get_current_user(),
        current_mode=data_mode,
        recommendations=data["recommendations"],
        total_items=data["total_items"],
        urgent_count=data["urgent_count"],
        total_units_recommended=data["total_units_recommended"],
        total_investment_estimated=data["total_investment_estimated"],
        stores=data["stores"],
        selected_store=store_id,
        draft_requests=draft_requests
    )

@app.route("/data-explorer")
@login_required
def data_explorer_page():
    """Page 9: Direct SQLite Data Explorer and CSV Bulk Ingestion."""
    table_name = request.args.get("table", default="inventory", type=str)
    search = request.args.get("search", type=str)
    limit = min(request.args.get("limit", default=50, type=int), 100)
    offset = max(request.args.get("offset", default=0, type=int), 0)
    data_mode = request.args.get("data_mode", default="all", type=str)

    data = DashboardService.get_data_explorer_data(
        table_name=table_name,
        search=search,
        limit=limit,
        offset=offset,
        data_mode=data_mode
    )

    return render_template(
        "data_explorer.html",
        active_page="data-explorer",
        page_heading="SQLite Data Explorer",
        page_subheading="Direct Relational Database Viewer & CSV Ingestion",
        current_user=get_current_user(),
        current_mode=data_mode,
        selected_table=data["table_name"],
        available_tables=data["available_tables"],
        columns=data["columns"],
        rows=data["rows"],
        total_rows=data["total_rows"],
        limit=limit,
        offset=offset,
        search=search
    )

# --------------------------------------------------------------------------
# Asynchronous REST API Endpoints
# --------------------------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    data = request.get_json(silent=True) or {}
    res = AuthService.register_user(
        full_name=data.get("full_name"),
        email=data.get("email"),
        password=data.get("password"),
        confirm_password=data.get("confirm_password"),
        business_name=data.get("business_name"),
        ip_address=request.remote_addr
    )
    if res["success"]:
        user = res["user"]
        session["user_id"] = user["user_id"]
        session["user_email"] = user["email"]
        session["user_name"] = user["full_name"]
        return jsonify(res), 201
    return jsonify(res), 400

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    res = AuthService.authenticate_user(
        email=data.get("email"),
        password=data.get("password"),
        ip_address=request.remote_addr
    )
    if res["success"]:
        user = res["user"]
        session["user_id"] = user["user_id"]
        session["user_email"] = user["email"]
        session["user_name"] = user["full_name"]
        return jsonify(res), 200
    return jsonify(res), 401

@app.route("/api/auth/demo-login", methods=["POST"])
def api_auth_demo_login():
    demo_user = AuthService.ensure_demo_user()
    session["user_id"] = demo_user["user_id"]
    session["user_email"] = demo_user["email"]
    session["user_name"] = demo_user["full_name"]
    return jsonify({"success": True, "message": "Logged in as Demo Manager.", "user": demo_user}), 200

@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully."}), 200

@app.route("/api/auth/me", methods=["GET"])
@app.route("/api/auth/status", methods=["GET"])
def api_auth_me():
    if "user_id" in session:
        user = AuthService.get_user_by_id(session["user_id"])
        if user:
            return jsonify({"authenticated": True, "logged_in": True, "user": user})
    return jsonify({"authenticated": False, "logged_in": False, "user": None})

@app.route("/api/status", methods=["GET"])
def api_status():
    has_gemini = bool(os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip())
    return jsonify({
        "status": "healthy",
        "app_name": APP_NAME,
        "track_id": TRACK_ID,
        "version": VERSION,
        "reference_date": REFERENCE_DATE,
        "database": "SQLite (Local WAL)",
        "gemini_api": "Active" if has_gemini else "Fallback Mode (Verified Deterministic NLU)",
        "gemini_model": GEMINI_MODEL if has_gemini else None
    })

@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    store_id = request.args.get("store_id", type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)
    return jsonify(DashboardService.get_dashboard_overview(store_id=store_id, data_mode=data_mode))

@app.route("/api/copilot/query", methods=["POST"])
def api_copilot_query():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    store_id = payload.get("store_id")
    data_mode = payload.get("data_mode", "demo")
    user_id = session.get("user_id")

    if not query:
        return jsonify({"error": "Missing query parameter in request body."}), 400

    try:
        response = CopilotService.answer_query(
            query=query,
            store_id=store_id,
            data_mode=data_mode,
            user_id=user_id
        )
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error processing Copilot query: {e}", exc_info=True)
        return jsonify({"error": "Failed to process analytics query.", "message": str(e)}), 500

@app.route("/api/inventory", methods=["GET"])
def api_inventory():
    store_id = request.args.get("store_id", type=int)
    category_id = request.args.get("category_id", type=int)
    risk_filter = request.args.get("risk_filter", type=str)
    search = request.args.get("search", type=str)
    data_mode = request.args.get("data_mode", default="demo", type=str)

    data = DashboardService.get_inventory_page_data(
        store_id=store_id,
        category_id=category_id,
        risk_filter=risk_filter,
        search=search,
        data_mode=data_mode
    )
    return jsonify(data)

@app.route("/api/sales", methods=["GET"])
def api_sales():
    store_id = request.args.get("store_id", type=int)
    days = request.args.get("days", default=30, type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)
    return jsonify(DashboardService.get_sales_page_data(store_id=store_id, days=days, data_mode=data_mode))

@app.route("/api/alerts", methods=["GET"])
def api_alerts():
    store_id = request.args.get("store_id", type=int)
    data_mode = request.args.get("data_mode", default="demo", type=str)
    return jsonify(DashboardService.get_alerts_page_data(store_id=store_id, data_mode=data_mode))

@app.route("/api/products", methods=["GET"])
def api_products():
    category_id = request.args.get("category_id", type=int)
    search = request.args.get("search", type=str)
    data_mode = request.args.get("data_mode", default="demo", type=str)
    return jsonify(DashboardService.get_products_page_data(category_id=category_id, search=search, data_mode=data_mode))

@app.route("/api/stores", methods=["GET"])
def api_stores():
    data_mode = request.args.get("data_mode", default="demo", type=str)
    return jsonify(DashboardService.get_stores_page_data(data_mode=data_mode))

@app.route("/api/explorer", methods=["GET"])
def api_explorer():
    table_name = request.args.get("table", default="inventory", type=str)
    search = request.args.get("search", type=str)
    limit = min(request.args.get("limit", default=50, type=int), 100)
    offset = max(request.args.get("offset", default=0, type=int), 0)
    data_mode = request.args.get("data_mode", default="all", type=str)

    data = DashboardService.get_data_explorer_data(
        table_name=table_name,
        search=search,
        limit=limit,
        offset=offset,
        data_mode=data_mode
    )
    return jsonify(data)

# --------------------------------------------------------------------------
# Manual Data Entry Endpoints
# --------------------------------------------------------------------------
@app.route("/api/data/store", methods=["POST"])
def api_add_store():
    data = request.get_json(silent=True) or {}
    res = DataService.add_store(
        name=data.get("name"),
        city=data.get("city"),
        code=data.get("code"),
        address=data.get("address"),
        manager_name=data.get("manager_name"),
        phone=data.get("phone"),
        user_id=session.get("user_id")
    )
    return jsonify(res), 201 if res["success"] else 400

@app.route("/api/data/product", methods=["POST"])
def api_add_product():
    data = request.get_json(silent=True) or {}
    res = DataService.add_product(
        sku=data.get("sku"),
        name=data.get("name"),
        category_id=data.get("category_id", 1),
        cost_price=data.get("cost_price", 0),
        selling_price=data.get("selling_price", 0),
        supplier_name=data.get("supplier_name"),
        lead_time_days=data.get("lead_time_days", 7),
        min_reorder_qty=data.get("min_reorder_qty", 10),
        user_id=session.get("user_id")
    )
    return jsonify(res), 201 if res["success"] else 400

@app.route("/api/data/inventory", methods=["POST"])
def api_add_inventory():
    data = request.get_json(silent=True) or {}
    res = DataService.add_inventory(
        store_id=data.get("store_id"),
        product_id=data.get("product_id"),
        current_stock=data.get("current_stock"),
        safety_stock=data.get("safety_stock", 10),
        reorder_level=data.get("reorder_level"),
        inventory_date=data.get("inventory_date"),
        user_id=session.get("user_id")
    )
    return jsonify(res), 201 if res["success"] else 400

@app.route("/api/data/sale", methods=["POST"])
def api_add_sale():
    data = request.get_json(silent=True) or {}
    res = DataService.add_sale(
        date=data.get("date"),
        store_id=data.get("store_id"),
        product_id=data.get("product_id"),
        units_sold=data.get("units_sold"),
        unit_price=data.get("unit_price"),
        user_id=session.get("user_id")
    )
    return jsonify(res), 201 if res["success"] else 400

@app.route("/api/data/import-csv", methods=["POST"])
def api_import_csv():
    table_type = request.form.get("table_type")
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No CSV file uploaded."}), 400

    csv_file = request.files["file"]
    if not csv_file.filename.lower().endswith(".csv"):
        return jsonify({"success": False, "error": "Only .csv files are supported."}), 400

    try:
        content = csv_file.read().decode("utf-8", errors="replace")
        res = DataService.import_csv_data(table_type=table_type, csv_text=content, user_id=session.get("user_id"))
        return jsonify(res), 200 if res["success"] else 400
    except Exception as e:
        logger.error(f"Error parsing uploaded CSV: {e}", exc_info=True)
        return jsonify({"success": False, "error": f"Failed to process CSV: {str(e)}"}), 500

# --------------------------------------------------------------------------
# Reorder Action Endpoints (Human-in-the-Loop)
# --------------------------------------------------------------------------
@app.route("/api/action/reorder", methods=["POST"])
@app.route("/api/reorders/create", methods=["POST"])
def api_action_reorder():
    payload = request.get_json(silent=True) or {}
    res = DataService.create_reorder_request(
        store_id=payload.get("store_id"),
        product_id=payload.get("product_id"),
        quantity=payload.get("quantity", 0),
        urgency=payload.get("urgency", "Normal"),
        notes=payload.get("notes"),
        user_id=session.get("user_id")
    )
    return jsonify(res), 201 if res["success"] else 400

@app.route("/api/reorders", methods=["GET"])
def api_get_reorders():
    data_mode = request.args.get("data_mode", default="demo", type=str)
    reorders = DataService.get_reorder_requests(limit=50, data_mode=data_mode)
    return jsonify({"success": True, "reorders": reorders, "total": len(reorders)})

@app.route("/api/reorders/status", methods=["POST"])
def api_update_reorder_status():
    payload = request.get_json(silent=True) or {}
    res = DataService.update_reorder_status(
        request_id=payload.get("request_id"),
        new_status=payload.get("status"),
        user_id=session.get("user_id")
    )
    return jsonify(res), 200 if res["success"] else 400

@app.route("/api/audit-logs", methods=["GET"])
def api_audit_logs():
    limit = request.args.get("limit", default=50, type=int)
    logs = DataService.get_audit_logs(limit=limit)
    return jsonify({"success": True, "logs": logs, "total": len(logs)})

# --------------------------------------------------------------------------
# Error Handlers
# --------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    return redirect(url_for("root"))

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal server error: {e}", exc_info=True)
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error occurred."}), 500
    flash("An unexpected server error occurred. Please try again.", "error")
    return redirect(url_for("root"))

# --------------------------------------------------------------------------
# Main Execution Entrypoint
# --------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("=" * 65)
    logger.info(f"Starting {APP_TITLE} (Track: {TRACK_ID})")
    logger.info(f"Serving at: http://localhost:{PORT}")
    logger.info("=" * 65)

    init_db()
    seed_database(force=False)
    AuthService.ensure_demo_user()

    app.run(host=HOST, port=PORT, debug=DEBUG)
