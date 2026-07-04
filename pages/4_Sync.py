import streamlit as st
import pandas as pd
import requests
import time
from utils.db import run_query
from utils.auth import verify_session

# ==============================================================================
# 1. SECURITY CHECK
# ==============================================================================
session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None

if not current_user:
    st.error("❌ Access Denied. Please log in.")
    st.stop()

st.title("🔄 Razorpay Sync Engine")
st.caption("Pull raw payment data from Razorpay and map it to your creators automatically.")

# ==============================================================================
# 2. CURRENT DATABASE STATS
# ==============================================================================
st.subheader("📊 Current Database Status")

stats_df = run_query("""
    SELECT 
        COUNT(*) as total, 
        COUNT(creator_id) as mapped, 
        COUNT(*) - COUNT(creator_id) as unmapped 
    FROM payments
""")

if not stats_df.empty:
    row = stats_df.iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Payments in DB", int(row['total']))
    m2.metric("Successfully Mapped", int(row['mapped']))
    m3.metric("Unmapped (Needs Review)", int(row['unmapped']))
else:
    st.info("Database is empty. Run the sync below to pull data.")

st.divider()

# ==============================================================================
# 3. SYNC ENGINE (Auto-Paginating Loop)
# ==============================================================================
st.subheader("🚀 Sync Engine")
st.info("Click the button below to fetch all 'captured' payments from Razorpay. It processes 100 at a time to ensure 100% accuracy without timing out.")

sync_clicked = st.button("🚀 Start Full Sync", type="primary", width='stretch')

if sync_clicked:
    vercel_url = st.secrets.get("VERCEL_API_URL")
    if not vercel_url:
        st.error("❌ Missing VERCEL_API_URL in Streamlit Secrets!")
        st.stop()

    # Clean URL just in case
    vercel_url = vercel_url.rstrip("/")
    
    cursor = None
    total_fetched = 0
    total_inserted = 0
    total_unmapped = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    status_text.text("🔄 Initializing connection to Razorpay...")
    
    while True:
        payload = {"to_timestamp": cursor} if cursor else {}
            
        try:
            resp = requests.post(f"{vercel_url}/api", json=payload, timeout=30)
            data = resp.json()
        except Exception as e:
            st.error(f"❌ Network Error talking to Vercel: {e}")
            break
            
        if not data.get("success"):
            st.error(f"❌ Sync Error: {data.get('error')}")
            break
            
        metrics = data.get("metrics", {})
        fetched = metrics.get("fetched", 0)
        
        total_fetched += fetched
        total_inserted += metrics.get("inserted", 0)
        total_unmapped += metrics.get("unmapped", 0)
        
        status_text.text(f"🔄 Syncing... (Fetched: {total_fetched} | Inserted: {total_inserted} | Unmapped: {total_unmapped})")
        
        # Visual progress (capped at 95% until we know we are done)
        progress_bar.progress(min(total_fetched / 500, 0.95)) 
        
        cursor = data.get("next_cursor")
        
        # If no cursor or we fetched 0 items, we are done
        if not cursor or fetched == 0:
            break
            
        # Prevent hitting Razorpay/Vercel rate limits
        time.sleep(0.5) 

    progress_bar.progress(100)
    st.success(f"✅ Sync Complete! Fetched {total_fetched} payments. {total_inserted} saved, {total_unmapped} unmapped.")
    
    if total_unmapped > 0:
        st.warning(f"⚠️ {total_unmapped} payments were unmapped. This means their Razorpay receipt didn't match any Creator Code in your database.")
        
    st.balloons()
    st.rerun() # Refresh the page to show the new stats

st.divider()

# ==============================================================================
# 4. RECENT PAYMENTS TABLE
# ==============================================================================
st.subheader("💳 Latest Synced Payments")
st.info("Check the 'Mapped Handle' column. If it's blank, the receipt in Razorpay didn't match any Creator Code.")

payments_df = run_query("""
    SELECT 
        p.payment_id,
        p.created_at,
        p.original_currency,
        p.amount_inr,
        p.status,
        p.receipt,
        c.creator_handle
    FROM payments p
    LEFT JOIN creators c ON p.creator_id = c.id
    ORDER BY p.created_at DESC
    LIMIT 20
""")

if payments_df.empty:
    st.warning("No payments found in the database yet. Run the sync above!")
else:
    display_df = payments_df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['amount_inr'] = display_df['amount_inr'] / 100.0
    
    st.dataframe(
        display_df,
        column_config={
            "payment_id": st.column_config.TextColumn("Payment ID", width="small"),
            "created_at": st.column_config.TextColumn("Date", width="small"),
            "original_currency": st.column_config.TextColumn("Currency", width="small"),
            "amount_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "receipt": st.column_config.TextColumn("Razorpay Receipt", width="medium"),
            "creator_handle": st.column_config.TextColumn("Mapped Handle", width="medium")
        },
        hide_index=True,
        width='stretch'
    )
