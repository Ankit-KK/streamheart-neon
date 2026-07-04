import streamlit as st
import pandas as pd
import psycopg2

@st.cache_resource
def get_connection():
    db_url = st.secrets.get("NEON_DATABASE_URL")
    if not db_url:
        st.error("❌ Add NEON_DATABASE_URL to Streamlit Secrets!")
        st.stop()
    return psycopg2.connect(db_url, sslmode="require")

def run_query(query, params=None):
    conn = get_connection()
    try:
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
