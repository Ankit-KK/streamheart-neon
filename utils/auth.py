import streamlit as st
import bcrypt
from utils.db import run_query

# 🔥 FIX: Point to the table Neon Auth already created!
# (If your Neon Auth setup named it something else like 'auth_user', change it here)
AUTH_TABLE = '"user"' 

def get_admin_count():
    """Checks if any users exist in the Neon Auth database."""
    df = run_query(f"SELECT COUNT(*) as count FROM {AUTH_TABLE}")
    return df.iloc[0]['count'] if not df.empty else 0

def create_admin(email, password):
    """Hashes the password and saves the new admin to Neon Auth's user table."""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Note: Neon Auth's 'user' table usually requires specific columns. 
    # If it fails, we might need to adjust the INSERT statement to match Neon Auth's exact schema.
    run_query(
        f"INSERT INTO {AUTH_TABLE} (email, password) VALUES (%s, %s)", 
        (email, hashed)
    )

def verify_login(email, password):
    """Checks the provided password against the stored hash in Neon Auth."""
    df = run_query(f"SELECT password FROM {AUTH_TABLE} WHERE email = %s", (email,))
    
    if df.empty:
        return False
        
    stored_hash = df.iloc[0]['password']
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
