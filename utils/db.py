import streamlit as st
import pandas as pd
import psycopg2

def run_query(query, params=None):
    db_url = st.secrets.get("NEON_DATABASE_URL")
    if not db_url:
        st.error("❌ Add NEON_DATABASE_URL to Streamlit Secrets!")
        st.stop()
        
    conn = None
    try:
        # 🔥 FIX: Open a fresh connection every time. 
        # This completely prevents "connection already closed" errors.
        conn = psycopg2.connect(db_url, sslmode="require")
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            
            # If the query returns data (like a SELECT), convert to DataFrame
            if cur.description:
                cols = [desc[0] for desc in cur.description]
                return pd.DataFrame(cur.fetchall(), columns=cols)
            # If it's an INSERT/UPDATE, commit and return empty DataFrame
            else:
                conn.commit()
                return pd.DataFrame()
                
    except Exception as e:
        st.error(f"🔴 Database Error: {e}")
        return pd.DataFrame()
        
    finally:
        # 🔥 FIX: Always close the connection when done to prevent memory leaks
        if conn:
            conn.close()
