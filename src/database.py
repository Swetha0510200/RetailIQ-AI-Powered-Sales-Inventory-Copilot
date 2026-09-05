"""
RetailIQ Database Manager
SQLite connection handling, schema initialization, migrations, and query execution.
"""

import sqlite3
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.config import DATABASE_PATH, DATA_DIR
from src.utils.logging_config import logger

def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection configured with dict-like row access."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable performance and integrity pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    """Safely adds missing columns to existing SQLite tables."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table});")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    for col_name, col_def in columns.items():
        if col_name not in existing_cols:
            logger.info(f"Migrating schema: Adding column {col_name} to table {table}")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def};")
    conn.commit()

def init_db() -> None:
    """Creates database schema and runs safe migrations."""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            business_name TEXT,
            created_at TEXT NOT NULL
        );
        """)

        # 2. Stores Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            store_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            address TEXT NOT NULL,
            manager_name TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            is_demo INTEGER DEFAULT 1,
            user_id INTEGER
        );
        """)

        # 3. Categories Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            target_turnover_days INTEGER DEFAULT 30
        );
        """)

        # 4. Products Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            cost_price REAL NOT NULL,
            selling_price REAL NOT NULL,
            supplier_name TEXT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            min_reorder_qty INTEGER NOT NULL,
            is_demo INTEGER DEFAULT 1,
            user_id INTEGER,
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        );
        """)

        # 5. Inventory Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            current_stock INTEGER NOT NULL CHECK(current_stock >= 0),
            reorder_level INTEGER NOT NULL CHECK(reorder_level >= 0),
            safety_stock INTEGER NOT NULL CHECK(safety_stock >= 0),
            last_restock_date TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_demo INTEGER DEFAULT 1,
            user_id INTEGER,
            UNIQUE(store_id, product_id),
            FOREIGN KEY (store_id) REFERENCES stores(store_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        """)

        # 6. Daily Sales Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            store_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            units_sold INTEGER NOT NULL CHECK(units_sold >= 0),
            unit_price REAL NOT NULL,
            revenue REAL NOT NULL,
            cost REAL NOT NULL,
            profit REAL NOT NULL,
            is_demo INTEGER DEFAULT 1,
            user_id INTEGER,
            FOREIGN KEY (store_id) REFERENCES stores(store_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        """)

        # 7. Reorder Requests Table (Human-in-the-Loop approval drafts)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reorder_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            estimated_cost REAL NOT NULL,
            urgency TEXT NOT NULL,
            status TEXT DEFAULT 'Draft / Pending Review',
            created_at TEXT NOT NULL,
            user_id INTEGER,
            notes TEXT,
            FOREIGN KEY (store_id) REFERENCES stores(store_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        """)

        # 8. Audit Trail Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id INTEGER,
            user_email TEXT,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT
        );
        """)

        # Indexes for lightning-fast aggregation and query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_store_prod ON sales(store_id, product_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventory_store_prod ON inventory(store_id, product_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reorders_status ON reorder_requests(status);")
        
        conn.commit()

        # Run safe migrations for tables that already existed
        for tbl in ["stores", "products", "inventory", "sales"]:
            _ensure_columns(conn, tbl, {
                "is_demo": "INTEGER DEFAULT 1",
                "user_id": "INTEGER"
            })

    logger.info("Database schema and migrations verified successfully.")

def fetch_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Executes SELECT query and returns rows as dictionaries."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def fetch_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """Executes SELECT query and returns single row as dictionary."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

def execute_write(query: str, params: tuple = ()) -> int:
    """Executes INSERT/UPDATE/DELETE query and returns affected rows or lastrowid."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid or cursor.rowcount
