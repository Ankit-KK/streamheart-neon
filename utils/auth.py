import streamlit as st
import bcrypt
import secrets
from datetime import datetime, timedelta, timezone
from utils.db import run_query

# ==============================================================================
# PASSWORD HASHING
# ==============================================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

# ==============================================================================
# USER MANAGEMENT
# ==============================================================================
def get_user_by_email(email: str) -> dict | None:
    df = run_query("SELECT id, email, password_hash, role, status FROM admin_users WHERE email = %s", (email.lower().strip(),))
    if df.empty:
        return None
    return df.iloc[0].to_dict()

def create_user(email: str, password: str, role: str = "SUPER_ADMIN") -> bool:
    hashed = hash_password(password)
    try:
        run_query(
            "INSERT INTO admin_users (email, password_hash, role) VALUES (%s, %s, %s)",
            (email.lower().strip(), hashed, role)
        )
        return True
    except Exception:
        return False

def get_all_users() -> list:
    df = run_query("SELECT id, email, role, status, created_at FROM admin_users ORDER BY created_at DESC")
    return df.to_dict('records') if not df.empty else []

def suspend_user(user_id: str):
    run_query("UPDATE admin_users SET status = 'SUSPENDED', updated_at = NOW() WHERE id = %s", (user_id,))
    revoke_all_sessions(user_id)

def activate_user(user_id: str):
    run_query("UPDATE admin_users SET status = 'ACTIVE', updated_at = NOW() WHERE id = %s", (user_id,))

def change_password(user_id: str, new_password: str):
    hashed = hash_password(new_password)
    run_query("UPDATE admin_users SET password_hash = %s, updated_at = NOW() WHERE id = %s", (hashed, user_id))
    revoke_all_sessions(user_id)

def get_user_count() -> int:
    df = run_query("SELECT COUNT(*) as count FROM admin_users")
    return int(df.iloc[0]['count']) if not df.empty else 0

# ==============================================================================
# SESSION MANAGEMENT (The Magic)
# ==============================================================================
def create_session(user_id: str, days: int = 7) -> str:
    """Creates a new session token and saves it to the database."""
    # Clean up old sessions first
    run_query("SELECT fn_cleanup_expired_sessions()")
    
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    
    run_query(
        "INSERT INTO admin_sessions (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user_id, token, expires)
    )
    return token

def verify_session(token: str) -> dict | None:
    """Checks if a session token is valid and returns the user data."""
    if not token:
        return None
        
    df = run_query("""
        SELECT u.id, u.email, u.role, u.status 
        FROM admin_sessions s
        JOIN admin_users u ON s.user_id = u.id
        WHERE s.token = %s AND s.expires_at > NOW()
    """, (token,))
    
    if df.empty:
        return None
    
    user = df.iloc[0].to_dict()
    
    # If the user was suspended after the session was created, reject it
    if user['status'] != 'ACTIVE':
        return None
        
    return user

def revoke_session(token: str):
    """Instantly kills a specific session (Logout)."""
    run_query("DELETE FROM admin_sessions WHERE token = %s", (token,))

def revoke_all_sessions(user_id: str):
    """Instantly kills ALL sessions for a user (Force Logout)."""
    run_query("DELETE FROM admin_sessions WHERE user_id = %s", (user_id,))

# ==============================================================================
# PASSWORD RESET
# ==============================================================================
def create_reset_token(email: str) -> str | None:
    """Generates a password reset token for the user."""
    user = get_user_by_email(email)
    if not user:
        return None
    
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    
    run_query(
        "INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user['id'], token, expires)
    )
    return token

def reset_password_with_token(token: str, new_password: str) -> bool:
    """Resets the password using a valid reset token."""
    df = run_query("""
        SELECT user_id FROM password_resets 
        WHERE token = %s AND expires_at > NOW() AND used = FALSE
    """, (token,))
    
    if df.empty:
        return False
    
    user_id = str(df.iloc[0]['user_id'])
    hashed = hash_password(new_password)
    
    run_query("UPDATE admin_users SET password_hash = %s, updated_at = NOW() WHERE id = %s", (hashed, user_id))
    run_query("UPDATE password_resets SET used = TRUE WHERE token = %s", (token,))
    revoke_all_sessions(user_id)
    
    return True
