import streamlit as st
from utils.db import run_query

st.title("🔍 Database Diagnostic")
st.info("This page reads your Neon database schema to find the exact Neon Auth tables and columns.")

# 1. Find all tables in the public schema
tables_df = run_query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
st.markdown("### 📂 Tables in Database:")
if not tables_df.empty:
    st.dataframe(tables_df, hide_index=True)
    
    # 2. Find columns for each table
    for table in tables_df['table_name']:
        # We use parameterized queries to safely check column names
        cols_df = run_query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s", 
            (table,)
        )
        st.markdown(f"#### 📋 Columns in `{table}`:")
        if not cols_df.empty:
            st.dataframe(cols_df, hide_index=True)
        else:
            st.warning("No columns found (might be a reserved word requiring quotes).")
else:
    st.error("No tables found in the 'public' schema!")
