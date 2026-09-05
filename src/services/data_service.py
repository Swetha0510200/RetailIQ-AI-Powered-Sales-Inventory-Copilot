"""
RetailIQ Data Management & Audit Service
Handles manual retail data entry, CSV bulk imports, reorder drafts, and audit logging.
"""

import csv
import io
from datetime import datetime
from typing import Dict, Any, List, Optional
from src.database import fetch_all, fetch_one, execute_write
from src.utils.validation import validate_date_string, validate_numeric_bounds
from src.utils.logging_config import logger

class DataService:
    # ----------------------------------------------------------------------
    # Audit Trail Logging
    # ----------------------------------------------------------------------
    @staticmethod
    def log_audit(
        action: str,
        details: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """Appends an immutable event to the audit_logs SQLite table."""
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            execute_write("""
                INSERT INTO audit_logs (timestamp, user_id, user_email, action, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (now_str, user_id, user_email or "system", action, details, ip_address or "127.0.0.1"))
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    @staticmethod
    def get_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent audit logs for administrative transparency."""
        return fetch_all("""
            SELECT log_id, timestamp, user_email, action, details, ip_address
            FROM audit_logs
            ORDER BY log_id DESC
            LIMIT ?;
        """, (limit,))

    # ----------------------------------------------------------------------
    # Manual Retail Data Entry
    # ----------------------------------------------------------------------
    @staticmethod
    def add_store(
        name: str,
        city: str,
        code: str,
        address: Optional[str] = None,
        manager_name: Optional[str] = None,
        phone: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Validates and saves a new retail store into SQLite."""
        name = str(name or "").strip()
        city = str(city or "").strip()
        code = str(code or "").strip().upper()
        address = str(address or "").strip() or f"{name}, {city}"
        manager_name = str(manager_name or "").strip() or "Store Manager"
        phone = str(phone or "").strip() or "N/A"

        if not name:
            return {"success": False, "error": "Store name is required."}
        if not city:
            return {"success": False, "error": "Store city/location is required."}
        if not code:
            return {"success": False, "error": "Store code is required."}

        # Check unique code
        existing = fetch_one("SELECT store_id FROM stores WHERE code = ?;", (code,))
        if existing:
            return {"success": False, "error": f"Store with code '{code}' already exists."}

        store_id = execute_write("""
            INSERT INTO stores (code, name, city, address, manager_name, contact_phone, is_active, is_demo, user_id)
            VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?);
        """, (code, name, city, address, manager_name, phone, user_id))

        DataService.log_audit(
            action="DATA_INSERTION_STORE",
            details=f"Created store '{name}' ({code}) in {city}",
            user_id=user_id
        )

        logger.info(f"Added store: {name} ({code}) by user {user_id}")
        return {
            "success": True,
            "message": f"Store '{name}' ({code}) added successfully.",
            "store_id": store_id,
            "code": code
        }

    @staticmethod
    def add_product(
        sku: str,
        name: str,
        category_id: int,
        cost_price: float,
        selling_price: float,
        supplier_name: Optional[str] = None,
        lead_time_days: int = 7,
        min_reorder_qty: int = 10,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Validates and inserts a new product SKU into the catalogue."""
        sku = str(sku or "").strip().upper()
        name = str(name or "").strip()
        supplier_name = str(supplier_name or "").strip() or "Standard Supplier"

        if not sku:
            return {"success": False, "error": "Product SKU cannot be empty."}
        if not name:
            return {"success": False, "error": "Product name cannot be empty."}
        
        try:
            category_id = int(category_id)
            cost_price = float(cost_price)
            selling_price = float(selling_price)
            lead_time_days = int(lead_time_days)
            min_reorder_qty = int(min_reorder_qty)
        except (ValueError, TypeError):
            return {"success": False, "error": "Prices, category, and lead times must be valid numbers."}

        if cost_price < 0 or selling_price < 0:
            return {"success": False, "error": "Unit cost and selling price cannot be negative."}
        if lead_time_days <= 0:
            return {"success": False, "error": "Lead time days must be greater than 0."}
        if min_reorder_qty <= 0:
            return {"success": False, "error": "Minimum reorder quantity must be at least 1."}

        # Check unique SKU
        existing = fetch_one("SELECT product_id FROM products WHERE sku = ?;", (sku,))
        if existing:
            return {"success": False, "error": f"Product with SKU '{sku}' already exists."}

        product_id = execute_write("""
            INSERT INTO products (sku, name, category_id, cost_price, selling_price, supplier_name, lead_time_days, min_reorder_qty, is_demo, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
        """, (sku, name, category_id, cost_price, selling_price, supplier_name, lead_time_days, min_reorder_qty, user_id))

        DataService.log_audit(
            action="DATA_INSERTION_PRODUCT",
            details=f"Created product SKU '{sku}' - {name}",
            user_id=user_id
        )

        logger.info(f"Added product SKU: {sku} ({name}) by user {user_id}")
        return {
            "success": True,
            "message": f"Product '{name}' ({sku}) added successfully.",
            "product_id": product_id,
            "sku": sku
        }

    @staticmethod
    def add_inventory(
        store_id: int,
        product_id: int,
        current_stock: int,
        safety_stock: int = 10,
        reorder_level: Optional[int] = None,
        inventory_date: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Validates and creates or updates a store inventory record."""
        try:
            store_id = int(store_id)
            product_id = int(product_id)
            current_stock = int(current_stock)
            safety_stock = int(safety_stock)
        except (ValueError, TypeError):
            return {"success": False, "error": "Store, product, and stock numbers must be valid integers."}

        if current_stock < 0:
            return {"success": False, "error": "Current stock quantity cannot be negative."}
        if safety_stock < 0:
            return {"success": False, "error": "Safety stock cannot be negative."}

        if reorder_level is None or int(reorder_level) < safety_stock:
            reorder_level = safety_stock + 15
        else:
            reorder_level = int(reorder_level)

        from src.config import REFERENCE_DATE
        inv_date = str(inventory_date or "").strip() or REFERENCE_DATE
        if not validate_date_string(inv_date):
            inv_date = REFERENCE_DATE

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Upsert inventory record
        existing = fetch_one("SELECT inventory_id FROM inventory WHERE store_id = ? AND product_id = ?;", (store_id, product_id))
        if existing:
            execute_write("""
                UPDATE inventory 
                SET current_stock = ?, safety_stock = ?, reorder_level = ?, last_restock_date = ?, updated_at = ?, is_demo = 0, user_id = ?
                WHERE store_id = ? AND product_id = ?;
            """, (current_stock, safety_stock, reorder_level, inv_date, now_str, user_id, store_id, product_id))
            action_msg = "Updated"
        else:
            execute_write("""
                INSERT INTO inventory (store_id, product_id, current_stock, reorder_level, safety_stock, last_restock_date, updated_at, is_demo, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?);
            """, (store_id, product_id, current_stock, reorder_level, safety_stock, inv_date, now_str, user_id))
            action_msg = "Created"

        DataService.log_audit(
            action="DATA_INSERTION_INVENTORY",
            details=f"{action_msg} inventory for store {store_id}, product {product_id}: stock = {current_stock}",
            user_id=user_id
        )

        logger.info(f"Inventory saved: store {store_id}, product {product_id}, stock {current_stock}")
        return {
            "success": True,
            "message": f"Inventory {action_msg.lower()} successfully ({current_stock} units).",
            "current_stock": current_stock,
            "store_id": store_id,
            "product_id": product_id
        }

    @staticmethod
    def add_sale(
        store_id: int,
        product_id: int,
        date: Optional[str] = None,
        units_sold: Optional[int] = None,
        unit_price: Optional[float] = None,
        user_id: Optional[int] = None,
        sale_date: Optional[str] = None,
        quantity: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Validates and records an individual daily sales transaction, updating stock."""
        actual_date = str(sale_date or date or "").strip()
        if not validate_date_string(actual_date):
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}

        actual_units = quantity if quantity is not None else units_sold
        if actual_units is None:
            return {"success": False, "error": "Units sold / quantity is required."}

        try:
            store_id = int(store_id)
            product_id = int(product_id)
            actual_units = int(actual_units)
        except (ValueError, TypeError):
            return {"success": False, "error": "Store, product, and units sold must be numbers."}

        if actual_units < 0:
            return {"success": False, "error": "Units sold cannot be negative."}

        prod = fetch_one("SELECT selling_price, cost_price FROM products WHERE product_id = ?;", (product_id,))
        if not prod:
            return {"success": False, "error": "Product not found."}

        price = float(unit_price) if unit_price is not None and float(unit_price) >= 0 else float(prod["selling_price"])
        cost_p = float(prod["cost_price"])

        revenue = round(actual_units * price, 2)
        cost = round(actual_units * cost_p, 2)
        profit = round(revenue - cost, 2)

        sale_id = execute_write("""
            INSERT INTO sales (date, store_id, product_id, units_sold, unit_price, revenue, cost, profit, is_demo, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
        """, (actual_date, store_id, product_id, actual_units, price, revenue, cost, profit, user_id))

        # Decrement store inventory
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        execute_write("""
            UPDATE inventory 
            SET current_stock = MAX(0, current_stock - ?), updated_at = ?
            WHERE store_id = ? AND product_id = ?;
        """, (actual_units, now_str, store_id, product_id))

        inv_row = fetch_one("SELECT current_stock FROM inventory WHERE store_id = ? AND product_id = ?;", (store_id, product_id))
        remaining_stock = inv_row["current_stock"] if inv_row else 0

        DataService.log_audit(
            action="DATA_INSERTION_SALE",
            details=f"Recorded sale: {actual_units} units of product {product_id} at store {store_id} on {actual_date}",
            user_id=user_id
        )

        logger.info(f"Sale recorded: ID {sale_id}, {actual_units} units on {actual_date}, remaining stock: {remaining_stock}")
        return {
            "success": True,
            "message": f"Sale of {actual_units} units (₹{revenue:,.2f}) recorded successfully.",
            "sale_id": sale_id,
            "quantity": actual_units,
            "units_sold": actual_units,
            "remaining_stock": remaining_stock
        }

    # ----------------------------------------------------------------------
    # CSV Bulk Import
    # ----------------------------------------------------------------------
    @staticmethod
    def import_csv_data(table_type: str, csv_text: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Parses, validates, and inserts bulk CSV records.
        Never silently discards rows; returns detailed rejected row diagnostics.
        """
        table_type = str(table_type or "").strip().lower()
        if table_type not in ("stores", "products", "inventory", "sales"):
            return {"success": False, "error": "Unsupported table type for CSV import."}

        if not csv_text or not csv_text.strip():
            return {"success": False, "error": "CSV file content is empty."}

        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        
        imported = 0
        errors: List[str] = []

        # 1. Stores CSV Import
        if table_type == "stores":
            required = {"name", "city", "code"}
            if not required.issubset(set(headers)):
                return {"success": False, "error": f"Missing required headers: {required - set(headers)}. Expected: code, name, city, address, manager_name, phone"}

            for idx, row in enumerate(reader, start=2):
                res = DataService.add_store(
                    name=row.get("name"),
                    city=row.get("city"),
                    code=row.get("code"),
                    address=row.get("address"),
                    manager_name=row.get("manager_name"),
                    phone=row.get("phone") or row.get("contact_phone"),
                    user_id=user_id
                )
                if res["success"]:
                    imported += 1
                else:
                    errors.append(f"Row {idx} ('{row.get('name')}'): {res['error']}")

        # 2. Products CSV Import
        elif table_type == "products":
            required = {"sku", "name", "cost_price", "selling_price"}
            if not required.issubset(set(headers)):
                return {"success": False, "error": f"Missing required headers: {required - set(headers)}. Expected at minimum: sku, name, cost_price, selling_price"}

            cats = fetch_all("SELECT category_id, name FROM categories;")
            cat_map = {c["name"].lower(): c["category_id"] for c in cats}

            for idx, row in enumerate(reader, start=2):
                try:
                    cat_val = row.get("category_id") or row.get("category") or "1"
                    if str(cat_val).strip().isdigit():
                        cat_id = int(cat_val)
                    else:
                        cat_id = cat_map.get(str(cat_val).strip().lower(), 1)

                    res = DataService.add_product(
                        sku=row.get("sku"),
                        name=row.get("name"),
                        category_id=cat_id,
                        cost_price=float(row.get("cost_price", 0)),
                        selling_price=float(row.get("selling_price", 0)),
                        supplier_name=row.get("supplier_name"),
                        lead_time_days=int(row.get("lead_time_days", 7) or 7),
                        min_reorder_qty=int(row.get("min_reorder_qty", 10) or 10),
                        user_id=user_id
                    )
                    if res["success"]:
                        imported += 1
                    else:
                        errors.append(f"Row {idx} ('{row.get('sku')}'): {res['error']}")
                except Exception as e:
                    errors.append(f"Row {idx}: Data parsing failed ({str(e)})")

        # 3. Inventory CSV Import
        elif table_type == "inventory":
            required = {"store_id", "product_id", "current_stock"}
            if not required.issubset(set(headers)):
                return {"success": False, "error": f"Missing required headers: {required - set(headers)}. Expected: store_id, product_id, current_stock, safety_stock, reorder_level, inventory_date"}

            for idx, row in enumerate(reader, start=2):
                try:
                    res = DataService.add_inventory(
                        store_id=int(row.get("store_id", 0)),
                        product_id=int(row.get("product_id", 0)),
                        current_stock=int(row.get("current_stock", 0)),
                        safety_stock=int(row.get("safety_stock", 10)),
                        reorder_level=int(row["reorder_level"]) if row.get("reorder_level") else None,
                        inventory_date=row.get("inventory_date"),
                        user_id=user_id
                    )
                    if res["success"]:
                        imported += 1
                    else:
                        errors.append(f"Row {idx}: {res['error']}")
                except Exception as e:
                    errors.append(f"Row {idx}: Data parsing failed ({str(e)})")

        # 4. Sales CSV Import
        elif table_type == "sales":
            required = {"date", "store_id", "product_id", "units_sold"}
            if not required.issubset(set(headers)):
                return {"success": False, "error": f"Missing required headers: {required - set(headers)}. Expected: date, store_id, product_id, units_sold, unit_price"}

            for idx, row in enumerate(reader, start=2):
                try:
                    res = DataService.add_sale(
                        date=row.get("date"),
                        store_id=int(row.get("store_id", 0)),
                        product_id=int(row.get("product_id", 0)),
                        units_sold=int(row.get("units_sold", 0)),
                        unit_price=float(row["unit_price"]) if row.get("unit_price") else None,
                        user_id=user_id
                    )
                    if res["success"]:
                        imported += 1
                    else:
                        errors.append(f"Row {idx}: {res['error']}")
                except Exception as e:
                    errors.append(f"Row {idx}: Data parsing failed ({str(e)})")

        DataService.log_audit(
            action=f"CSV_IMPORT_{table_type.upper()}",
            details=f"Imported {imported} rows into {table_type}; {len(errors)} errors",
            user_id=user_id
        )

        return {
            "success": imported > 0,
            "imported_count": imported,
            "skipped_count": len(errors),
            "error_count": len(errors),
            "errors": errors[:20],
            "message": f"Successfully imported {imported} {table_type} record(s)." + (f" ({len(errors)} rows rejected)" if errors else "")
        }

    # ----------------------------------------------------------------------
    # Reorder Requests (Human-in-the-Loop approval tracking)
    # ----------------------------------------------------------------------
    @staticmethod
    def create_reorder_request(
        store_id: int,
        product_id: int,
        quantity: int,
        urgency: str = "Normal",
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
        source: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Creates a local SQLite reorder draft record.
        Respects human-in-the-loop: does not falsely claim an external vendor dispatch.
        """
        try:
            store_id = int(store_id)
            product_id = int(product_id)
            quantity = int(quantity)
        except (ValueError, TypeError):
            return {"success": False, "error": "Invalid store, product, or quantity parameters."}

        if quantity <= 0:
            return {"success": False, "error": "Order quantity must be greater than zero."}

        prod = fetch_one("SELECT name, cost_price, supplier_name FROM products WHERE product_id = ?;", (product_id,))
        store = fetch_one("SELECT name FROM stores WHERE store_id = ?;", (store_id,))

        if not prod or not store:
            return {"success": False, "error": "Product or Store record not found."}

        cost_est = round(quantity * float(prod["cost_price"]), 2)
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        req_id = execute_write("""
            INSERT INTO reorder_requests (store_id, product_id, quantity, estimated_cost, urgency, status, created_at, user_id, notes)
            VALUES (?, ?, ?, ?, ?, 'Draft / Pending Review', ?, ?, ?);
        """, (store_id, product_id, quantity, cost_est, urgency, now_str, user_id, notes or f"Automated draft for {prod['supplier_name']}"))

        DataService.log_audit(
            action="REORDER_REQUEST_CREATED",
            details=f"Created reorder draft #{req_id} for {quantity} units of {prod['name']} at {store['name']} (Est. ₹{cost_est:,.2f})",
            user_id=user_id
        )

        logger.info(f"Reorder request #{req_id} created for {quantity} units of {prod['name']}")
        return {
            "success": True,
            "request_id": req_id,
            "recommended_quantity": quantity,
            "status": "Draft / Pending Review",
            "message": f"Draft replenishment order #{req_id} saved for {quantity} units of {prod['name']}. Status: Draft / Pending Review.",
            "details": {
                "request_id": req_id,
                "product_name": prod["name"],
                "store_name": store["name"],
                "supplier_name": prod["supplier_name"],
                "quantity": quantity,
                "estimated_cost": cost_est,
                "urgency": urgency,
                "status": "Draft / Pending Review",
                "human_notice": "Draft created locally for manager approval before external supplier dispatch."
            }
        }

    @staticmethod
    def get_reorder_requests(limit: int = 50, data_mode: str = "all", **kwargs) -> List[Dict[str, Any]]:
        """Fetches all local reorder requests with product and store details."""
        return fetch_all("""
            SELECT 
                r.request_id, r.quantity, r.quantity as recommended_quantity, r.estimated_cost, r.urgency, r.status, r.created_at, r.notes,
                p.product_id, p.name as product_name, p.sku, p.supplier_name,
                s.store_id, s.name as store_name
            FROM reorder_requests r
            JOIN products p ON r.product_id = p.product_id
            JOIN stores s ON r.store_id = s.store_id
            ORDER BY r.request_id DESC
            LIMIT ?;
        """, (limit,))

    @staticmethod
    def update_reorder_status(request_id: int, new_status: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Updates review status of a reorder request (e.g. Approved, Ordered, Fulfilled, Cancelled)."""
        status_map = {
            "draft": "Draft / Pending Review",
            "draft / pending review": "Draft / Pending Review",
            "pending": "Draft / Pending Review",
            "approved": "approved",
            "ordered": "ordered",
            "fulfilled": "fulfilled",
            "cancelled": "cancelled",
            "canceled": "cancelled"
        }
        normalized = status_map.get(str(new_status or "").strip().lower(), str(new_status or "").strip())
        valid_statuses = {"Draft / Pending Review", "Approved", "Ordered", "Fulfilled", "Cancelled", "approved", "ordered", "fulfilled", "cancelled"}
        if normalized not in valid_statuses:
            return {"success": False, "error": f"Invalid status. Must be one of {valid_statuses}"}

        updated = execute_write("""
            UPDATE reorder_requests SET status = ? WHERE request_id = ?;
        """, (normalized, request_id))

        if updated:
            if normalized.lower() == "fulfilled":
                req = fetch_one("SELECT store_id, product_id, quantity FROM reorder_requests WHERE request_id = ?;", (request_id,))
                if req:
                    from src.config import REFERENCE_DATE
                    execute_write("""
                        UPDATE inventory 
                        SET current_stock = current_stock + ?, last_restock_date = ?
                        WHERE store_id = ? AND product_id = ?;
                    """, (req["quantity"], REFERENCE_DATE, req["store_id"], req["product_id"]))

            DataService.log_audit(
                action="REORDER_STATUS_CHANGED",
                details=f"Updated reorder request #{request_id} to '{normalized}'",
                user_id=user_id
            )
            return {"success": True, "status": normalized, "message": f"Order #{request_id} status updated to '{normalized}'."}
        return {"success": False, "error": "Reorder request not found."}
