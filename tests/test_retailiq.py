"""
RetailIQ Automated Test Suite
Verifies deterministic calculations, grounding, alert engine, REST APIs, and restraint.
"""

import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import io
from app import app
from src.database import get_connection, init_db, fetch_one, fetch_all, execute_write
from src.seed_data import seed_database
from src.analytics.inventory import get_inventory_status, get_inventory_summary
from src.analytics.sales import get_kpis, detect_sales_anomalies, get_store_performance, get_top_products
from src.analytics.alerts import generate_alerts
from src.analytics.recommendations import get_reorder_recommendations
from src.services.copilot_service import CopilotService
from src.services.auth_service import AuthService
from src.services.data_service import DataService

class TestRetailIQ(unittest.TestCase):
    @classmethod
    def _cleanup_test_data(cls):
        """Clean up non-demo test records respecting foreign key dependency ordering."""
        try:
            execute_write("DELETE FROM sales WHERE is_demo = 0 OR store_id NOT IN (1, 2, 3, 4);")
            execute_write("DELETE FROM inventory WHERE is_demo = 0 OR store_id NOT IN (1, 2, 3, 4);")
            execute_write("DELETE FROM reorder_requests WHERE store_id NOT IN (1, 2, 3, 4) OR product_id > 50;")
            execute_write("DELETE FROM stores WHERE is_demo = 0 OR store_id NOT IN (1, 2, 3, 4);")
            execute_write("DELETE FROM products WHERE is_demo = 0 OR product_id > 50;")
            execute_write("DELETE FROM users WHERE email != 'demo@retailiq.ai';")
        except Exception as e:
            logger.warning(f"Error in _cleanup_test_data: {e}")

    @classmethod
    def setUpClass(cls):
        """Set up test environment and initialize database."""
        init_db()
        seed_database(force=False)
        cls._cleanup_test_data()
        # Ensure showcase stock for Mouse at Chennai Central is exact
        execute_write("UPDATE inventory SET current_stock = 18 WHERE store_id = 1 AND product_id = 2;")
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        """Clean up test records after all tests have completed."""
        cls._cleanup_test_data()
        # Ensure showcase stock for Mouse at Chennai Central remains restored
        execute_write("UPDATE inventory SET current_stock = 18 WHERE store_id = 1 AND product_id = 2;")

    def test_01_database_seed_integrity(self):
        """Verify stores, categories, products, inventory, and sales are populated."""
        stores_cnt = fetch_one("SELECT COUNT(*) as c FROM stores;")["c"]
        self.assertEqual(stores_cnt, 4, "Must have 4 retail stores")

        cats_cnt = fetch_one("SELECT COUNT(*) as c FROM categories;")["c"]
        self.assertEqual(cats_cnt, 7, "Must have 7 product categories")

        prods_cnt = fetch_one("SELECT COUNT(*) as c FROM products;")["c"]
        self.assertEqual(prods_cnt, 50, "Must have 50 products")

        inv_cnt = fetch_one("SELECT COUNT(*) as c FROM inventory;")["c"]
        self.assertEqual(inv_cnt, 200, "Must have 200 inventory records (4 stores x 50 products)")

        sales_cnt = fetch_one("SELECT COUNT(*) as c FROM sales;")["c"]
        self.assertGreater(sales_cnt, 30000, "Must have >30,000 sales records covering 6 months")

    def test_02_showcase_product_stockout(self):
        """Verify Product B (Wireless Optical Mouse) at Chennai Central is flagged critical stock-out."""
        items = get_inventory_status(store_id=1)
        mouse_item = next((it for it in items if it["product_id"] == 2), None)
        self.assertIsNotNone(mouse_item, "Wireless Optical Mouse must exist")
        self.assertEqual(mouse_item["risk_level"], "critical_stockout")
        self.assertLessEqual(mouse_item["days_remaining"], 7.0)
        self.assertIn("Urgent: Reorder", mouse_item["recommended_action"])

    def test_03_showcase_product_overstock(self):
        """Verify Product C (Ergonomic Desk Mat) at Karur Main is flagged overstocked."""
        items = get_inventory_status(store_id=2)
        desk_mat = next((it for it in items if it["product_id"] == 15), None)
        self.assertIsNotNone(desk_mat, "Desk Mat must exist")
        self.assertEqual(desk_mat["risk_level"], "overstocked")
        self.assertGreater(desk_mat["days_remaining"], 60.0)

    def test_04_sales_anomalies_detection(self):
        """Verify sales spike (Earbuds at Coimbatore) and sales drop (Flask at Chennai) are detected."""
        anomalies = detect_sales_anomalies()
        spikes = anomalies["spikes"]
        drops = anomalies["drops"]

        self.assertGreater(len(spikes), 0, "Should detect at least one sales spike")
        earbuds_spike = next((s for s in spikes if s["product_id"] == 3 and s["store_id"] == 3), None)
        self.assertIsNotNone(earbuds_spike, "Earbuds spike at Coimbatore must be detected")
        self.assertGreaterEqual(earbuds_spike["velocity_ratio"], 1.5)

        self.assertGreater(len(drops), 0, "Should detect at least one sales drop")
        flask_drop = next((d for d in drops if d["product_id"] == 22 and d["store_id"] == 1), None)
        self.assertIsNotNone(flask_drop, "Flask drop at Chennai must be detected")
        self.assertLessEqual(flask_drop["velocity_ratio"], 0.6)

    def test_05_reorder_recommendations(self):
        """Verify reorder quantities are mathematically calculated."""
        reorders = get_reorder_recommendations()
        self.assertGreater(len(reorders), 0, "Must have reorder recommendations")
        for ro in reorders:
            self.assertGreater(ro["recommended_reorder_qty"], 0)
            self.assertIn("calculation_breakdown", ro)
            self.assertIn("assumptions", ro)

    def test_06_copilot_stockout_query(self):
        """Verify Copilot answers 'What products are likely to run out?' with evidence."""
        res = CopilotService.answer_query("What products are likely to run out?")
        self.assertEqual(res["intent"], "stock_out")
        self.assertGreater(len(res["evidence"]), 0, "Must provide verified evidence")
        self.assertTrue(res["is_grounded"])
        self.assertIn("Wireless Optical Mouse", str(res))

    def test_07_copilot_difficult_case_restraint(self):
        """Verify Copilot demonstrates strict restraint on unsupported queries."""
        unsupported_query = "Will the supplier deliver tomorrow?"
        res = CopilotService.answer_query(unsupported_query)
        self.assertEqual(res["intent"], "unsupported_query")
        self.assertIn("cannot determine that from the available data", res["summary"])
        self.assertIsNotNone(res["data_limitations"])
        self.assertEqual(len(res["details"]), 0)

    def test_08_api_endpoints(self):
        """Verify all REST API endpoints return 200 OK and valid JSON."""
        endpoints = [
            "/api/status",
            "/api/dashboard",
            "/api/inventory",
            "/api/sales",
            "/api/alerts",
            "/api/products",
            "/api/stores",
            "/api/explorer"
        ]
        for ep in endpoints:
            response = self.client.get(ep)
            self.assertEqual(response.status_code, 200, f"Endpoint {ep} must return 200 OK")
            json_data = response.get_json()
            self.assertIsInstance(json_data, dict, f"Endpoint {ep} must return JSON dict")

    def test_09_api_copilot_post(self):
        """Verify POST /api/copilot/query works."""
        payload = {"query": "Which store performed best?"}
        response = self.client.post("/api/copilot/query", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["intent"], "store_performance")
        self.assertIn("Chennai Central", data["summary"])

    def test_10_authentication_lifecycle(self):
        """Verify user registration, password hashing, duplicate check, login, and demo-login."""
        # 1. Register new user
        reg_res = self.client.post("/api/auth/register", json={
            "full_name": "Test Manager",
            "email": "testmanager@example.com",
            "password": "Password123!",
            "store_name": "Test Store"
        })
        self.assertEqual(reg_res.status_code, 201)
        reg_data = reg_res.get_json()
        self.assertTrue(reg_data["success"])
        self.assertEqual(reg_data["user"]["email"], "testmanager@example.com")

        # Verify password hash in SQLite is not plaintext
        user_row = fetch_one("SELECT password_hash FROM users WHERE email = 'testmanager@example.com';")
        self.assertIsNotNone(user_row)
        self.assertNotEqual(user_row["password_hash"], "Password123!")
        self.assertTrue(user_row["password_hash"].startswith("scrypt:") or user_row["password_hash"].startswith("pbkdf2:"))

        # 2. Reject duplicate email
        dup_res = self.client.post("/api/auth/register", json={
            "full_name": "Duplicate User",
            "email": "testmanager@example.com",
            "password": "AnotherPassword!",
        })
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("already exists", dup_res.get_json()["error"])

        # 3. Login with incorrect password
        bad_login = self.client.post("/api/auth/login", json={
            "email": "testmanager@example.com",
            "password": "WrongPassword!"
        })
        self.assertEqual(bad_login.status_code, 401)

        # 4. Login with correct password
        good_login = self.client.post("/api/auth/login", json={
            "email": "testmanager@example.com",
            "password": "Password123!"
        })
        self.assertEqual(good_login.status_code, 200)
        self.assertTrue(good_login.get_json()["success"])

        # 5. Check /api/auth/me
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        self.assertTrue(me_res.get_json()["authenticated"])
        self.assertEqual(me_res.get_json()["user"]["email"], "testmanager@example.com")

        # 6. 1-Click Demo Login
        demo_res = self.client.post("/api/auth/demo-login")
        self.assertEqual(demo_res.status_code, 200)
        demo_data = demo_res.get_json()
        self.assertTrue(demo_data["success"])
        self.assertEqual(demo_data["user"]["email"], "demo@retailiq.ai")

        # 7. Logout
        logout_res = self.client.post("/api/auth/logout")
        self.assertEqual(logout_res.status_code, 200)
        me_after = self.client.get("/api/auth/me")
        self.assertFalse(me_after.get_json()["authenticated"])

    def test_11_data_service_manual_entry_validation(self):
        """Verify strict validation on manual data entry (reject negative values, invalid FKs, empty strings)."""
        # 1. Reject store with empty name or code
        res_st = DataService.add_store(name="", code="STR-ERR", city="City")
        self.assertFalse(res_st["success"])
        self.assertIn("Store name is required", res_st["error"])

        # 2. Add valid store
        st = DataService.add_store(name="Tirunelveli Hub", code="STR-TNV", city="Tirunelveli")
        self.assertTrue(st["success"])
        self.assertIn("store_id", st)
        self.assertEqual(st["code"], "STR-TNV" if "code" in st else st.get("store_id", st["store_id"]))

        # 3. Reject product with negative price
        res_p = DataService.add_product(
            name="Bad Price Product",
            sku="ERR-NEG-01",
            category_id=1,
            cost_price=100.0,
            selling_price=-50.0
        )
        self.assertFalse(res_p["success"])
        self.assertIn("cannot be negative", res_p["error"])

        # 4. Reject product with empty SKU
        res_sku = DataService.add_product(
            name="No SKU Product",
            sku="",
            category_id=1,
            cost_price=10.0,
            selling_price=20.0
        )
        self.assertFalse(res_sku["success"])
        self.assertIn("Product SKU cannot be empty", res_sku["error"])

        # 5. Add valid product
        p = DataService.add_product(
            name="USB-C Ultra Fast Cable",
            sku="ACC-USBC-99",
            category_id=1,
            cost_price=120.0,
            selling_price=299.0,
            lead_time_days=4,
            min_reorder_qty=20
        )
        self.assertTrue(p["success"])
        self.assertIn("product_id", p)

        # 6. Reject duplicate SKU
        res_dup = DataService.add_product(
            name="USB-C Duplicate",
            sku="ACC-USBC-99",
            category_id=1,
            cost_price=120.0,
            selling_price=299.0
        )
        self.assertFalse(res_dup["success"])
        self.assertIn("already exists", res_dup["error"])

        # 7. Add inventory and record sale
        inv = DataService.add_inventory(
            store_id=st["store_id"],
            product_id=p["product_id"],
            current_stock=50,
            safety_stock=10,
            reorder_level=20
        )
        self.assertTrue(inv["success"])
        self.assertEqual(inv["current_stock"], 50)

        sale = DataService.add_sale(
            store_id=st["store_id"],
            product_id=p["product_id"],
            quantity=5,
            sale_date="2026-09-04",
            unit_price=299.0
        )
        self.assertTrue(sale["success"])
        self.assertEqual(sale["quantity"], 5)
        self.assertEqual(sale["remaining_stock"], 45)

    def test_12_bulk_csv_import(self):
        """Verify CSV bulk import with column validation and error reporting."""
        # 1. Valid store CSV
        csv_stores = (
            "code,name,city,state,manager_name,phone\n"
            "STR-CSV1,Thanjavur Branch,Thanjavur,Tamil Nadu,K. Rajan,+91 94441 12345\n"
            "STR-CSV2,Dindigul West,Dindigul,Tamil Nadu,P. Mani,+91 94441 67890\n"
        )
        res1 = DataService.import_csv_data("stores", csv_stores)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["imported_count"], 2)
        self.assertEqual(len(res1["errors"]), 0)

        # 2. Malformed CSV with missing required columns
        csv_bad = "some_random_column,another_column\nval1,val2\n"
        res2 = DataService.import_csv_data("stores", csv_bad)
        self.assertFalse(res2["success"])
        self.assertIn("Missing required headers", res2["error"])

        # 3. CSV with partial row validation failures
        csv_mixed = (
            "sku,name,category,cost_price,selling_price,supplier_name,lead_time_days,min_reorder_qty\n"
            "CSV-PROD-01,Valid Product 1,Electronics,100,200,Supplier A,5,10\n"
            ",Missing SKU Product,Electronics,100,200,Supplier A,5,10\n"
            "CSV-PROD-02,Negative Price,Electronics,-50,200,Supplier A,5,10\n"
        )
        res3 = DataService.import_csv_data("products", csv_mixed)
        self.assertTrue(res3["success"])
        self.assertEqual(res3["imported_count"], 1)
        self.assertEqual(res3["skipped_count"], 2)
        self.assertEqual(len(res3["errors"]), 2)

    def test_13_reorder_requests_human_in_the_loop(self):
        """Verify draft replenishment order creation and status lifecycle without claiming external supplier dispatch."""
        # Create draft reorder
        draft = DataService.create_reorder_request(
            store_id=1,
            product_id=2, # Wireless Mouse
            quantity=35,
            user_id=None,
            source="manual_modal"
        )
        self.assertIn("request_id", draft)
        self.assertEqual(draft["status"], "Draft / Pending Review")
        self.assertEqual(draft["recommended_quantity"], 35)

        # Verify it is listed in pending reorders
        orders = DataService.get_reorder_requests(data_mode="all")
        found = next((o for o in orders if o["request_id"] == draft["request_id"]), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["status"], "Draft / Pending Review")

        # Approve draft
        app_res = DataService.update_reorder_status(draft["request_id"], "approved")
        self.assertTrue(app_res["success"])
        self.assertEqual(app_res["status"], "approved")

        # Mark ordered
        ord_res = DataService.update_reorder_status(draft["request_id"], "ordered")
        self.assertTrue(ord_res["success"])
        self.assertEqual(ord_res["status"], "ordered")

    def test_14_data_mode_isolation(self):
        """Verify data isolation across demo mode, user mode, and combined all mode."""
        # 1. Demo mode returns pre-seeded dataset
        demo_inv = get_inventory_status(store_id=None, data_mode="demo")
        self.assertGreaterEqual(len(demo_inv), 200)

        # 2. User mode without user records returns 0 or only user records
        user_inv = get_inventory_status(store_id=None, data_mode="user")
        # Every item in user_inv must have is_demo = 0
        for it in user_inv:
            raw = fetch_one(f"SELECT is_demo FROM inventory WHERE inventory_id = {it['inventory_id']};")
            self.assertEqual(raw["is_demo"], 0)

        # 3. Combined all mode includes both
        all_inv = get_inventory_status(store_id=None, data_mode="all")
        self.assertGreaterEqual(len(all_inv), len(demo_inv))

    def test_15_audit_trail_logging(self):
        """Verify system activity and audit trail captures changes."""
        logs = DataService.get_audit_logs(limit=20)
        self.assertIsInstance(logs, list)
        self.assertGreater(len(logs), 0, "Audit logs must record prior actions")

        # Verify audit log endpoint
        res = self.client.get("/api/audit-logs")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["logs"], list)

    def test_16_page_routes_and_auth_protection(self):
        """Verify unauthenticated access redirects to /login and authenticated access serves 200 OK for all required pages."""
        # 1. Unauthenticated requests to protected pages must redirect (302) to /login
        protected_pages = [
            "/",
            "/dashboard",
            "/copilot",
            "/inventory",
            "/products",
            "/stores",
            "/sales",
            "/alerts",
            "/recommendations",
            "/data-explorer"
        ]
        # Create fresh client without session
        anon_client = app.test_client()
        for p in protected_pages:
            res = anon_client.get(p, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Unauthenticated GET {p} must redirect")
            self.assertIn("/login", res.headers.get("Location", ""), f"{p} must redirect to /login")

        # 2. Public auth pages must return 200
        res_login = anon_client.get("/login")
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b"RetailIQ", res_login.data)
        self.assertIn(b"Store Manager Email", res_login.data)

        res_register = anon_client.get("/register")
        self.assertEqual(res_register.status_code, 200)
        self.assertIn(b"Create Account", res_register.data)

        # 3. Log in with demo user
        auth_client = app.test_client()
        login_res = auth_client.post("/login", data={
            "email": "manager@retailiq.internal",
            "password": "RetailIQ2026!"
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)
        self.assertIn(b"Executive Retail Dashboard", login_res.data)

        # 4. Now verify all protected pages return 200 for authenticated user
        test_pages = [
            ("/dashboard", b"Executive Retail Dashboard"),
            ("/copilot", b"AI Copilot"),
            ("/inventory", b"Inventory Management & Stock Health"),
            ("/products", b"Product Master Catalog"),
            ("/stores", b"Retail Stores & Regional Network"),
            ("/sales", b"Sales Transactions & Demand Velocity"),
            ("/alerts", b"Prioritized Operational Alerts"),
            ("/recommendations", b"Deterministic Replenishment Recommendations"),
            ("/data-explorer", b"SQLite Data Explorer & Audit Trail")
        ]
        for url, expected_text in test_pages:
            res = auth_client.get(url)
            self.assertEqual(res.status_code, 200, f"Authenticated {url} must return 200")
            self.assertIn(expected_text, res.data, f"{url} must render its page heading")

        # 5. Logout and verify protected pages are locked again
        logout_res = auth_client.get("/logout", follow_redirects=True)
        self.assertEqual(logout_res.status_code, 200)
        self.assertIn(b"Store Manager Email", logout_res.data)

        dash_after = auth_client.get("/dashboard", follow_redirects=False)
        self.assertEqual(dash_after.status_code, 302)
        self.assertIn("/login", dash_after.headers.get("Location", ""))

    def test_17_full_user_flow(self):
        """Execute full user flow: Register -> Login -> Add Store -> Add Product -> Add Inventory -> Add Sale -> Copilot -> Logout."""
        client = app.test_client()
        unique_email = f"flow_manager_{os.getpid()}@example.com"

        # Register
        reg = client.post("/register", data={
            "full_name": "Flow Test User",
            "email": unique_email,
            "business_name": "Flow Retail Ltd",
            "password": "FlowPassword2026!",
            "confirm_password": "FlowPassword2026!"
        }, follow_redirects=True)
        self.assertEqual(reg.status_code, 200)

        # Login
        log = client.post("/login", data={
            "email": unique_email,
            "password": "FlowPassword2026!"
        }, follow_redirects=True)
        self.assertEqual(log.status_code, 200)
        self.assertIn(b"Executive Retail Dashboard", log.data)

        # Add Store via API
        st_res = client.post("/api/data/store", json={
            "code": f"STR-FLW-{os.getpid() % 1000}",
            "name": "Flow Branch West",
            "city": "Madurai",
            "address": "10 West Masi St, Madurai",
            "manager_name": "Flow Test User",
            "phone": "+91 98888 77777"
        })
        self.assertEqual(st_res.status_code, 201)
        store_id = st_res.get_json()["store_id"]

        # Add Product
        prod_res = client.post("/api/data/product", json={
            "sku": f"SKU-FLW-{os.getpid() % 1000}",
            "name": "Flow Wireless Keyboard",
            "category_id": 1,
            "cost_price": 600.0,
            "selling_price": 1200.0,
            "supplier_name": "Flow Supply Co",
            "lead_time_days": 5,
            "min_reorder_qty": 20
        })
        self.assertEqual(prod_res.status_code, 201)
        product_id = prod_res.get_json()["product_id"]

        # Add Inventory
        inv_res = client.post("/api/data/inventory", json={
            "store_id": store_id,
            "product_id": product_id,
            "current_stock": 100,
            "safety_stock": 15,
            "reorder_level": 30,
            "inventory_date": "2026-09-04"
        })
        self.assertEqual(inv_res.status_code, 201)

        # Add Sale
        sale_res = client.post("/api/data/sale", json={
            "date": "2026-09-04",
            "store_id": store_id,
            "product_id": product_id,
            "units_sold": 10,
            "unit_price": 1200.0
        })
        self.assertEqual(sale_res.status_code, 201)

        # Ask Copilot
        copilot_res = client.post("/api/copilot/query", json={
            "query": "Which products are at risk of stockout?",
            "data_mode": "all"
        })
        self.assertEqual(copilot_res.status_code, 200)
        self.assertIn("intent", copilot_res.get_json())

        # Logout
        logout = client.get("/logout", follow_redirects=True)
        self.assertEqual(logout.status_code, 200)
        self.assertIn(b"Store Manager Email", logout.data)

if __name__ == "__main__":
    unittest.main()

