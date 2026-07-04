import streamlit as st
from utils.db import run_query

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")
st.title("💖 StreamHeart CMS (Debug Mode)")

st.markdown("### 🔍 Database Schema Inspector")
st.info("Reading Neon database to find Neon Auth tables and columns...")

# 1. Get all tables in the public schema
tables_df = run_query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")

if tables_df.empty:
    st.error("❌ No tables found in the 'public' schema! Check your NEON_DATABASE_URL in Streamlit Secrets.")
else:
    st.success(f"✅ Found {len(tables_df)} tables in your database.")
    st.dataframe(tables_df, hide_index=True, use_container_width=True)
    
    st.divider()
    
    # 2. Get columns for each table
    for table in tables_df['table_name']:
        st.markdown(f"#### 📋 Columns in `{table}`:")
        
        # We query the columns and their data types
        cols_df = run_query(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position;", 
            (table,)
        )
        
        if not cols_df.empty:
            st.dataframe(cols_df, hide_index=True, use_container_width=True)
        else:
            st.warning(f"⚠️ Could not read columns for `{table}` (This usually happens if the table name is a reserved SQL word like 'user' and needs quotes).")
