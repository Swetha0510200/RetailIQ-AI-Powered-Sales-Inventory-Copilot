"""
RetailIQ Authentication & User Management Service
Provides secure local SQLite authentication with Werkzeug password hashing.
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from src.database import fetch_one, execute_write
from src.utils.logging_config import logger

EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

class AuthService:
    @staticmethod
    def ensure_demo_user() -> Dict[str, Any]:
        """Ensures default demo manager users are present for 1-click judge evaluation."""
        demo_accounts = [
            ("demo@retailiq.ai", "Demo Store Manager", "RetailDemo2026!"),
            ("manager@retailiq.internal", "Retail Operations Manager", "RetailIQ2026!")
        ]
        first_user = None
        for email, name, pw in demo_accounts:
            user = fetch_one("SELECT user_id, full_name, email, business_name FROM users WHERE email = ?;", (email,))
            if not user:
                pw_hash = generate_password_hash(pw)
                created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                uid = execute_write("""
                    INSERT INTO users (full_name, email, password_hash, business_name, created_at)
                    VALUES (?, ?, ?, ?, ?);
                """, (name, email, pw_hash, "RetailIQ Retail Operations", created_at))
                user = {
                    "user_id": uid,
                    "full_name": name,
                    "email": email,
                    "business_name": "RetailIQ Retail Operations"
                }
            if not first_user:
                first_user = user
        return first_user

    @staticmethod
    def register_user(
        full_name: str,
        email: str,
        password: str,
        confirm_password: Optional[str] = None,
        business_name: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a new store manager with hashed password storage."""
        full_name = str(full_name or "").strip()
        email = str(email or "").strip().lower()
        business_name = str(business_name or "").strip() or "Independent Retail"
        password = str(password or "")

        if not full_name:
            return {"success": False, "error": "Full name is required."}
        if not email or not EMAIL_REGEX.match(email):
            return {"success": False, "error": "Please enter a valid email address."}
        if len(password) < 6:
            return {"success": False, "error": "Password must be at least 6 characters long."}
        if confirm_password is not None and password != confirm_password:
            return {"success": False, "error": "Passwords do not match."}

        # Check existing email
        existing = fetch_one("SELECT user_id FROM users WHERE email = ?;", (email,))
        if existing:
            return {"success": False, "error": "An account with this email already exists. Please log in."}

        pw_hash = generate_password_hash(password)
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        user_id = execute_write("""
            INSERT INTO users (full_name, email, password_hash, business_name, created_at)
            VALUES (?, ?, ?, ?, ?);
        """, (full_name, email, pw_hash, business_name, now_str))

        # Log audit trail
        from src.services.data_service import DataService
        DataService.log_audit(
            action="USER_REGISTERED",
            details=f"Registered account for {email} ({business_name})",
            user_id=user_id,
            user_email=email,
            ip_address=ip_address
        )

        logger.info(f"Successfully registered user: {email} (ID: {user_id})")
        return {
            "success": True,
            "message": "Account created successfully.",
            "user": {
                "user_id": user_id,
                "full_name": full_name,
                "email": email,
                "business_name": business_name
            }
        }

    @staticmethod
    def authenticate_user(email: str, password: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """Authenticates manager credentials against SQLite with secure hash comparison."""
        email = str(email or "").strip().lower()
        if not email or not password:
            return {"success": False, "error": "Email and password are required."}

        # Auto-seed demo user if demo credentials are used
        if email == "demo@retailiq.ai":
            AuthService.ensure_demo_user()

        user = fetch_one("SELECT user_id, full_name, email, password_hash, business_name FROM users WHERE email = ?;", (email,))
        if not user or not check_password_hash(user["password_hash"], password):
            from src.services.data_service import DataService
            DataService.log_audit(
                action="LOGIN_FAILED",
                details=f"Failed login attempt for {email}",
                user_email=email,
                ip_address=ip_address
            )
            return {"success": False, "error": "Invalid email or password."}

        from src.services.data_service import DataService
        DataService.log_audit(
            action="USER_LOGIN",
            details=f"Logged in successfully",
            user_id=user["user_id"],
            user_email=user["email"],
            ip_address=ip_address
        )

        logger.info(f"User authenticated: {email} (ID: {user['user_id']})")
        return {
            "success": True,
            "user": {
                "user_id": user["user_id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "business_name": user["business_name"]
            }
        }

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """Fetches public user record by primary key."""
        return fetch_one("SELECT user_id, full_name, email, business_name, created_at FROM users WHERE user_id = ?;", (user_id,))
