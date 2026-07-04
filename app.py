import streamlit as st
from utils.db import run_query

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")
st.title("💖 StreamHeart CMS (Debug Mode)")

st.markdown("### 🔍 Database Schema Inspector (All Schemas)")
st.info("Scanning all schemas (including 'auth') to find Neon Auth tables...")

# 1. Get all tables in ALL non-system schemas
tables_df = run_query("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name;
""")

if tables_df.empty:
    st.error("❌ No tables found in any schema!")
else:
    st.success(f"✅ Found {len(tables_df)} tables across all schemas.")
    st.dataframe(tables_df, hide_index=True, use_container_width=True)
    
    st.divider()
    
    # 2. Get columns for each table
    for index, row in tables_df.iterrows():
        schema = row['table_schema']
        table = row['table_name']
        
        st.markdown(f"#### 📋 Columns in `{schema}`.`{table}`:")
        
        cols_df = run_query(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position;", 
            (schema, table)
        )
        
        if not cols_df.empty:
            st.dataframe(cols_df, hide_index=True, use_container_width=True)
        else:
            st.warning(f"⚠️ Could not read columns for `{schema}`.`{table}`")
