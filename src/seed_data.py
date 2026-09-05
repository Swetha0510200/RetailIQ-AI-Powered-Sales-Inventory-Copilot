"""
RetailIQ Seed Data Generator
Populates the SQLite database with 6 months of realistic, coherent retail data.
Uses a fixed seed (42) for deterministic reproducibility.
"""

import random
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any

from src.config import REFERENCE_DATE, DATABASE_PATH
from src.database import get_connection, init_db
from src.utils.logging_config import logger

def seed_database(force: bool = False) -> None:
    """Generates and seeds stores, products, inventory, and 6 months of sales."""
    init_db()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM sales;")
        count = cursor.fetchone()["cnt"]
        if count > 0 and not force:
            logger.info(f"Database already contains {count} sales records. Skipping seed.")
            return

        logger.info("Generating realistic retail dataset with seed=42...")
        # Clear existing data for fresh seed
        cursor.execute("DELETE FROM sales;")
        cursor.execute("DELETE FROM inventory;")
        cursor.execute("DELETE FROM products;")
        cursor.execute("DELETE FROM categories;")
        cursor.execute("DELETE FROM stores;")

        random.seed(42)

        # -------------------------------------------------------------
        # 1. Stores (4 stores)
        # -------------------------------------------------------------
        stores_data = [
            ("STR-CHN", "Chennai Central", "Chennai", "102 Anna Salai, Chennai, TN", "Karthik Raja", "+91 98401 23456"),
            ("STR-KRR", "Karur Main", "Karur", "45 Kovai Road, Karur, TN", "Priya Sundaram", "+91 94432 34567"),
            ("STR-CBE", "Coimbatore Mall", "Coimbatore", "L-2 Brookefields, Coimbatore, TN", "Anand Natarajan", "+91 97890 45678"),
            ("STR-SLM", "Salem Junction", "Salem", "12 Meyyanur Bypass, Salem, TN", "Deepa Varma", "+91 98940 56789"),
        ]
        cursor.executemany("""
            INSERT INTO stores (code, name, city, address, manager_name, contact_phone)
            VALUES (?, ?, ?, ?, ?, ?);
        """, stores_data)

        # -------------------------------------------------------------
        # 2. Categories (7 categories)
        # -------------------------------------------------------------
        categories_data = [
            ("CAT-ELEC", "Electronics", "Gadgets, audio, computing peripherals and smart devices", 25),
            ("CAT-ACC", "Accessories", "Cables, chargers, bags, covers and desk gear", 30),
            ("CAT-HOME", "Home & Living", "Home decor, lighting, organization and comfort", 45),
            ("CAT-CARE", "Personal Care", "Grooming, skincare and wellness products", 20),
            ("CAT-STAT", "Stationery", "Notebooks, premium pens, desk utilities and art supplies", 40),
            ("CAT-GROC", "Grocery & Gourmet", "Dry groceries, tea, coffee, nuts and artisan snacks", 15),
            ("CAT-KITCH", "Kitchenware", "Cookware, flasks, food containers and dining accessories", 35),
        ]
        cursor.executemany("""
            INSERT INTO categories (code, name, description, target_turnover_days)
            VALUES (?, ?, ?, ?);
        """, categories_data)

        # -------------------------------------------------------------
        # 3. Products (50 items across 7 categories)
        # (sku, name, cat_id, cost, price, supplier, lead_time, min_reorder, base_vel)
        # -------------------------------------------------------------
        products_data = [
            # Electronics (cat_id: 1)
            ("SKU-EL-001", "Ergonomic Wireless Keyboard", 1, 1450.0, 2499.0, "LogiTech Solutions", 5, 20, 3.0),
            ("SKU-EL-002", "Wireless Optical Mouse", 1, 450.0, 899.0, "LogiTech Solutions", 5, 30, 4.2),  # Product B: Stockout showcase
            ("SKU-EL-003", "Noise Cancelling Earbuds", 1, 2200.0, 3999.0, "SonicWave Electronics", 7, 15, 2.1), # Product E: Spike showcase
            ("SKU-EL-004", "USB-C Multiport Hub 7-in-1", 1, 1100.0, 1999.0, "Ankerix Components", 6, 25, 2.8),
            ("SKU-EL-005", "Smart LED Desk Lamp", 1, 950.0, 1799.0, "LumaTech India", 8, 15, 1.9),
            ("SKU-EL-006", "Portable Bluetooth Speaker", 1, 1300.0, 2299.0, "SonicWave Electronics", 7, 20, 3.1),
            ("SKU-EL-007", "1080p HD Webcam with Mic", 1, 1600.0, 2899.0, "Visionary Devices", 10, 15, 1.7),
            ("SKU-EL-008", "Fast Wireless Charging Pad", 1, 650.0, 1299.0, "PowerGrid Accessories", 5, 30, 3.4),

            # Accessories (cat_id: 2)
            ("SKU-AC-009", "Braided Nylon USB-C Cable (2m)", 2, 180.0, 449.0, "Ankerix Components", 4, 50, 6.5),
            ("SKU-AC-010", "MagSafe Phone Mount", 2, 400.0, 899.0, "PowerGrid Accessories", 6, 30, 2.4),
            ("SKU-AC-011", "Laptop Sleeve 15.6 inch", 2, 550.0, 1199.0, "GearShield Co.", 7, 20, 2.2),
            ("SKU-AC-012", "Cable Management Clips (Pack of 6)", 2, 90.0, 249.0, "DeskZen Crafts", 3, 60, 4.8),
            ("SKU-AC-013", "Adjustable Aluminum Laptop Stand", 2, 850.0, 1699.0, "DeskZen Crafts", 7, 20, 2.5),
            ("SKU-AC-014", "Backpack Anti-Theft Water-Resistant", 2, 1400.0, 2799.0, "GearShield Co.", 10, 15, 1.4),
            ("SKU-AC-015", "Ergonomic Desk Mat Large", 2, 320.0, 799.0, "DeskZen Crafts", 5, 25, 0.8), # Product C: Overstock showcase
            ("SKU-AC-016", "Screen Cleaning Kit 200ml", 2, 120.0, 299.0, "ClearView Essentials", 4, 40, 3.8),

            # Home & Living (cat_id: 3)
            ("SKU-HM-017", "Aroma Diffuser Ultrasonic 300ml", 3, 750.0, 1499.0, "AuraLiving Organics", 8, 20, 1.8),
            ("SKU-HM-018", "Essential Oil Set (Lavender, Tea Tree)", 3, 300.0, 699.0, "AuraLiving Organics", 5, 30, 2.6),
            ("SKU-HM-019", "Memory Foam Lumbar Cushion", 3, 600.0, 1299.0, "ErgoRest Living", 7, 20, 1.9),
            ("SKU-HM-020", "Ceramic Plant Pot with Stand", 3, 400.0, 899.0, "GreenNest Decor", 9, 20, 1.3),
            ("SKU-HM-021", "Wall Clock Minimalist Nordic", 3, 500.0, 1099.0, "GreenNest Decor", 10, 15, 1.1),
            ("SKU-HM-022", "Stainless Steel Insulated Flask 1L", 3, 450.0, 999.0, "Thermovan Living", 6, 25, 5.5), # Product F: Drop showcase
            ("SKU-HM-023", "Fleece Throw Blanket", 3, 550.0, 1249.0, "CozyCrest Textiles", 12, 15, 1.2),

            # Personal Care (cat_id: 4)
            ("SKU-PC-024", "Organic Charcoal Face Wash 150ml", 4, 160.0, 349.0, "PureBotanics Ltd", 5, 40, 5.1),
            ("SKU-PC-025", "Beard Grooming Oil & Balm Kit", 4, 380.0, 799.0, "ManCraft Essentials", 6, 25, 2.3),
            ("SKU-PC-026", "SPF 50 Sunscreen Gel 100g", 4, 240.0, 499.0, "PureBotanics Ltd", 4, 50, 6.2),
            ("SKU-PC-027", "Electric Sonic Toothbrush", 4, 900.0, 1899.0, "DentPro Technologies", 8, 20, 1.6),
            ("SKU-PC-028", "Hair Nourishing Argan Serum 100ml", 4, 280.0, 599.0, "PureBotanics Ltd", 5, 30, 3.3),
            ("SKU-PC-029", "Hand Sanitizer Foam 250ml", 4, 90.0, 199.0, "CareFirst Hygiene", 3, 50, 4.5),
            ("SKU-PC-030", "Deep Hydrating Night Cream 50g", 4, 350.0, 749.0, "PureBotanics Ltd", 6, 25, 2.0),

            # Stationery (cat_id: 5)
            ("SKU-ST-031", "Hardbound Dotted Journal A5", 5, 220.0, 499.0, "PaperCraft Guild", 6, 30, 3.5),
            ("SKU-ST-032", "Gel Pen Box 0.5mm (Pack of 10)", 5, 110.0, 249.0, "PaperCraft Guild", 4, 50, 5.8),
            ("SKU-ST-033", "Dual Tip Pastel Highlighters (6pk)", 5, 140.0, 299.0, "ColorBurst Stationery", 5, 40, 4.0),
            ("SKU-ST-034", "Sticky Notes Assorted Pads (4pk)", 5, 80.0, 189.0, "ColorBurst Stationery", 3, 60, 4.7),
            ("SKU-ST-035", "Premium Calligraphy Pen Set", 5, 650.0, 1399.0, "MasterScribe Artisans", 12, 10, 0.1), # Product D: Slow-moving showcase
            ("SKU-ST-036", "Metal Mesh Desktop Organizer", 5, 280.0, 649.0, "DeskZen Crafts", 7, 25, 1.5),
            ("SKU-ST-037", "Mechanical Pencil 0.7mm Metal", 5, 150.0, 349.0, "MasterScribe Artisans", 6, 35, 2.2),

            # Grocery & Gourmet (cat_id: 6)
            ("SKU-GR-038", "Artisanal Dark Roast Coffee Beans 250g", 6, 260.0, 499.0, "Nilgiri Highlands Estate", 4, 30, 4.4),
            ("SKU-GR-039", "Cold-Pressed Virgin Coconut Oil 500ml", 6, 190.0, 369.0, "Kongu Valley Organics", 5, 35, 3.9),
            ("SKU-GR-040", "Raw Forest Honey 500g", 6, 250.0, 480.0, "Nilgiri Highlands Estate", 5, 30, 3.6),
            ("SKU-GR-041", "Premium Roasted Almonds 250g", 6, 280.0, 520.0, "NutriHarvest Naturals", 4, 40, 4.9),
            ("SKU-GR-042", "Organic Green Tea Leaves 100g", 6, 140.0, 289.0, "Nilgiri Highlands Estate", 4, 40, 3.7),
            ("SKU-GR-043", "Chia & Flax Seeds Superfood 200g", 6, 120.0, 249.0, "NutriHarvest Naturals", 5, 35, 2.7),
            ("SKU-GR-044", "Artisan Peanut Butter Crunchy 350g", 6, 150.0, 319.0, "Kongu Valley Organics", 4, 35, 3.2),

            # Kitchenware (cat_id: 7)
            ("SKU-KT-045", "Non-Stick Frying Pan 26cm", 7, 650.0, 1399.0, "ChefCraft Cookware", 8, 20, 2.1),
            ("SKU-KT-046", "Cast Iron Skillet Pre-Seasoned", 7, 850.0, 1799.0, "Heritage Ironworks", 10, 15, 1.6),
            ("SKU-KT-047", "Stainless Steel Lunch Box 3-Tier", 7, 350.0, 799.0, "Thermovan Living", 6, 25, 3.4),
            ("SKU-KT-048", "Glass Meal Prep Containers (Pack of 3)", 7, 500.0, 1099.0, "ClearView Essentials", 7, 20, 2.5),
            ("SKU-KT-049", "Silicone Cooking Utensils Set (6pc)", 7, 380.0, 849.0, "ChefCraft Cookware", 6, 25, 2.3),
            ("SKU-KT-050", "Bamboo Cutting Board with Groove", 7, 320.0, 699.0, "Heritage Ironworks", 7, 20, 2.4),
        ]

        for p in products_data:
            cursor.execute("""
                INSERT INTO products (sku, name, category_id, cost_price, selling_price, supplier_name, lead_time_days, min_reorder_qty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]))

        conn.commit()

        # -------------------------------------------------------------
        # 4. Generate 6 Months of Daily Sales (2026-03-01 to 2026-09-04)
        # 188 days total
        # -------------------------------------------------------------
        start_date = datetime(2026, 3, 1)
        end_date = datetime(2026, 9, 4)
        days_count = (end_date - start_date).days + 1

        # Store multiplier factors for realistic sales variance
        store_multipliers = {
            1: 1.25,  # Chennai Central (largest store)
            2: 0.85,  # Karur Main (smaller tier-2 hub)
            3: 1.15,  # Coimbatore Mall (busy retail mall)
            4: 0.95,  # Salem Junction (steady station/bypass hub)
        }

        sales_rows: List[tuple] = []
        product_base_velocities = {idx + 1: p[8] for idx, p in enumerate(products_data)}
        product_prices = {idx + 1: (p[3], p[4]) for idx, p in enumerate(products_data)}

        # Iterate through all days
        for day_offset in range(days_count):
            current_day = start_date + timedelta(days=day_offset)
            date_str = current_day.strftime("%Y-%m-%d")
            is_weekend = current_day.weekday() in (5, 6) # Saturday, Sunday
            weekend_boost = 1.30 if is_weekend else 1.0

            days_from_end = (end_date - current_day).days

            for store_id in range(1, 5):
                st_mult = store_multipliers[store_id]

                for product_id in range(1, 51):
                    base_vel = product_base_velocities[product_id]
                    cost_p, sell_p = product_prices[product_id]

                    # Deliberate Demo Scenario Sales Manipulations
                    effective_vel = base_vel * st_mult * weekend_boost

                    # Product E (SKU-EL-003 Noise Cancelling Earbuds) at Store 3 (Coimbatore):
                    # Recent spike in last 7 days (days_from_end <= 7)
                    if product_id == 3 and store_id == 3:
                        if days_from_end <= 7:
                            effective_vel = 6.8  # surge from 2.1 to 6.8
                        else:
                            effective_vel = 2.1

                    # Product F (SKU-HM-022 Stainless Steel Flask) at Store 1 (Chennai Central):
                    # Sudden drop in last 14 days
                    elif product_id == 22 and store_id == 1:
                        if days_from_end <= 14:
                            effective_vel = 1.8  # dropped from 5.5 to 1.8
                        else:
                            effective_vel = 5.5

                    # Product B (SKU-EL-002 Wireless Mouse) at Store 1 (Chennai Central):
                    # Steady high sales leading to stock-out
                    elif product_id == 2 and store_id == 1:
                        effective_vel = 4.2

                    # Product C (SKU-AC-015 Desk Mat) at Store 2 (Karur Main):
                    # Extremely low demand leading to massive overstock
                    elif product_id == 15 and store_id == 2:
                        effective_vel = 0.8

                    # Product D (SKU-ST-035 Premium Calligraphy Pen) at Store 4 (Salem):
                    # Very slow moving
                    elif product_id == 35 and store_id == 4:
                        effective_vel = 0.1

                    # Add realistic Poisson-like randomized daily fluctuation
                    # (ensure non-negative integer)
                    noise = random.uniform(0.7, 1.3)
                    expected_units = effective_vel * noise

                    # Probabilistic integer rounding
                    units = int(expected_units)
                    if random.random() < (expected_units - units):
                        units += 1

                    # Zero sales day chance for very slow products
                    if effective_vel < 0.3 and random.random() > effective_vel:
                        units = 0

                    if units > 0:
                        revenue = round(units * sell_p, 2)
                        cost = round(units * cost_p, 2)
                        profit = round(revenue - cost, 2)
                        sales_rows.append((
                            date_str, store_id, product_id, units, sell_p, revenue, cost, profit
                        ))

        cursor.executemany("""
            INSERT INTO sales (date, store_id, product_id, units_sold, unit_price, revenue, cost, profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, sales_rows)
        conn.commit()
        logger.info(f"Generated {len(sales_rows)} sales records across 4 stores and 188 days.")

        # -------------------------------------------------------------
        # 5. Inventory Setup (4 stores x 50 products = 200 records)
        # Seed realistic stock values that tell our deliberate stories!
        # -------------------------------------------------------------
        inventory_rows = []
        for store_id in range(1, 5):
            for idx, p in enumerate(products_data):
                product_id = idx + 1
                lead_time = p[6]
                base_vel = p[8]
                st_mult = store_multipliers[store_id]
                recent_avg = base_vel * st_mult

                # Default safe inventory formulas
                safety_stock = int(recent_avg * 7) + 5
                reorder_level = int(recent_avg * (lead_time + 2)) + safety_stock
                # Default stock: 20-30 days of sales
                current_stock = int(recent_avg * random.uniform(18, 28)) + safety_stock
                last_restock = (datetime.strptime(REFERENCE_DATE, "%Y-%m-%d") - timedelta(days=random.randint(5, 25))).strftime("%Y-%m-%d")

                # Override for our specific deliberate showcase items:
                # 1. Product B: Wireless Mouse (product_id 2) at Chennai Central (store_id 1)
                # Stockout Showcase: 18 units, 4.2 sales/day -> ~4.3 days left, lead time 5 days
                if product_id == 2 and store_id == 1:
                    current_stock = 18
                    safety_stock = 10
                    reorder_level = 35
                    last_restock = "2026-08-10"

                # 2. Product C: Desk Mat (product_id 15) at Karur Main (store_id 2)
                # Overstock Showcase: 350 units, 0.8 sales/day -> ~437 days left (>60 threshold)
                elif product_id == 15 and store_id == 2:
                    current_stock = 350
                    safety_stock = 8
                    reorder_level = 20
                    last_restock = "2026-08-28"

                # 3. Product D: Calligraphy Pen (product_id 35) at Salem (store_id 4)
                # Slow Moving Showcase: 0.1 sales/day, 45 units in stock
                elif product_id == 35 and store_id == 4:
                    current_stock = 45
                    safety_stock = 5
                    reorder_level = 10
                    last_restock = "2026-07-15"

                # 4. Product E: Earbuds (product_id 3) at Coimbatore (store_id 3)
                # Sales Spike Showcase: high velocity, 22 units left
                elif product_id == 3 and store_id == 3:
                    current_stock = 22
                    safety_stock = 15
                    reorder_level = 45
                    last_restock = "2026-08-20"

                # 5. Product F: Insulated Flask (product_id 22) at Chennai (store_id 1)
                # Sales Drop Showcase: 85 units left, demand cooled down
                elif product_id == 22 and store_id == 1:
                    current_stock = 85
                    safety_stock = 15
                    reorder_level = 50
                    last_restock = "2026-08-15"

                # 6. Product A: Ergonomic Keyboard (product_id 1) at Chennai (store_id 1)
                # Healthy Showcase: 45 units left, 3.0 sales/day -> ~15 days
                elif product_id == 1 and store_id == 1:
                    current_stock = 45
                    safety_stock = 12
                    reorder_level = 25
                    last_restock = "2026-08-22"

                # Additional realistic low stock and overstock items across other stores
                elif product_id == 9 and store_id == 4:  # Cable at Salem - low stock
                    current_stock = 12
                    safety_stock = 20
                    reorder_level = 45
                elif product_id == 20 and store_id == 3: # Plant pot at Coimbatore - overstock
                    current_stock = 120
                    safety_stock = 10
                    reorder_level = 25

                inventory_rows.append((
                    store_id, product_id, current_stock, reorder_level, safety_stock,
                    last_restock, REFERENCE_DATE
                ))

        cursor.executemany("""
            INSERT INTO inventory (store_id, product_id, current_stock, reorder_level, safety_stock, last_restock_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, inventory_rows)

        conn.commit()
        logger.info(f"Initialized {len(inventory_rows)} inventory records across all stores.")

if __name__ == "__main__":
    seed_database(force=True)
