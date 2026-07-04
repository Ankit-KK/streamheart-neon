import streamlit as st
import bcrypt
from utils.db import run_query

def get_admin_count():
    """Checks if any admins exist in the database."""
    df = run_query("SELECT COUNT(*) as count FROM admin_users")
    return df.iloc[0]['count'] if not df.empty else 0

def create_admin(email, password):
    """Hashes the password and saves the new admin to Neon."""
    # bcrypt automatically generates a salt and hashes the password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    run_query(
        "INSERT INTO admin_users (email, password_hash) VALUES (%s, %s)",
        (email, hashed)
    )

def verify_login(email, password):
    """Checks the provided password against the stored hash."""
    df = run_query("SELECT password_hash FROM admin_users WHERE email = %s", (email,))
    
    if df.empty:
        return False
        
    stored_hash = df.iloc[0]['password_hash']
    # bcrypt checks if the plain text password matches the stored hash
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
