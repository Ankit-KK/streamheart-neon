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
        conn = psycopg2.connect(db_url, sslmode="require")
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            
            if cur.description:
                cols = [desc[0] for desc in cur.description]
                return pd.DataFrame(cur.fetchall(), columns=cols)
            else:
                conn.commit()
                return pd.DataFrame()
                
    except Exception as e:
        st.error(f"🔴 Database Error: {e}")
        return pd.DataFrame()
        
    finally:
        if conn:
            conn.close()

def execute_transaction(queries_and_params: list):
    """
    Executes multiple SQL queries in a single atomic transaction.
    If any query fails, ALL changes are rolled back.
    """
    db_url = st.secrets.get("NEON_DATABASE_URL")
    if not db_url:
        st.error("❌ Add NEON_DATABASE_URL to Streamlit Secrets!")
        return False
        
    conn = None
    try:
        conn = psycopg2.connect(db_url, sslmode="require")
        with conn.cursor() as cur:
            for query, params in queries_and_params:
                cur.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"🔴 Transaction Failed (All changes reverted): {e}")
        return False
    finally:
        if conn:
            conn.close()
