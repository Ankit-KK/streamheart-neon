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
    st.error("❌ Access Denied.")
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

st.divider()

# ==============================================================================
# 3. SYNC ENGINE (FORWARD SYNCING)
# ==============================================================================
st.subheader("🚀 Razorpay Sync Engine (Fetch New Data Only)")
st.info("Fetches ONLY new payments from Razorpay. It checks your database for the latest payment and starts from there.")

sync_clicked = st.button("🚀 Start Razorpay Sync", type="primary", width='stretch')

if sync_clicked:
    vercel_url = st.secrets.get("VERCEL_API_URL").rstrip("/")
    
    # 🔥 FIX: Get the MAX created_at from the DB to start forward syncing
    max_time_df = run_query("SELECT MAX(created_at) as max_time FROM payments")
    from_timestamp = None
    if not max_time_df.empty and pd.notna(max_time_df.iloc[0]['max_time']):
        # Convert datetime to Unix timestamp
        max_time = pd.to_datetime(max_time_df.iloc[0]['max_time'])
        from_timestamp = int(max_time.timestamp())
        st.info(f"🕒 Resuming sync from: **{max_time.strftime('%Y-%m-%d %H:%M:%S')}**")
    else:
        st.warning("⚠️ Database is empty. Fetching the most recent 100 payments to start.")

    to_timestamp = None
    total_fetched = 0
    total_inserted = 0
    
    status_text = st.empty()
    
    while True:
        payload = {}
        if from_timestamp:
            payload["from_timestamp"] = from_timestamp
        if to_timestamp:
            payload["to_timestamp"] = to_timestamp
            
        status_text.text(f"🔄 Fetching batch... (From: {from_timestamp or 'Start'}, To: {to_timestamp or 'Now'})")
        
        try:
            resp = requests.post(f"{vercel_url}/api", json=payload, timeout=30)
            data = resp.json()
        except Exception as e:
            st.error(f"Network Error: {e}")
            break
            
        if not data.get("success"):
            st.error(f"Sync Error: {data.get('error')}")
            break
            
        metrics = data.get("metrics", {})
        fetched = metrics.get("fetched", 0)
        
        total_fetched += fetched
        total_inserted += metrics.get("inserted", 0)
        
        status_text.text(f"🔄 Syncing... (Fetched: {total_fetched} | Inserted: {total_inserted})")
        
        next_to = data.get("next_to")
        if not next_to or fetched == 0:
            break
            
        to_timestamp = next_to
        time.sleep(0.5)

    st.success(f"✅ Razorpay Sync Complete! Fetched {total_fetched} new payments.")
    st.balloons()
    st.rerun()

st.divider()

# ==============================================================================
# 4. RECENT PAYMENTS TABLE (WITH IST FIX)
# ==============================================================================
st.subheader("💳 Latest Synced Payments (IST)")

# 🔥 FIX: Added AT TIME ZONE 'Asia/Kolkata' to display IST time
payments_df = run_query("""
    SELECT p.payment_id, (p.created_at AT TIME ZONE 'Asia/Kolkata') as created_at, 
           p.original_currency, p.amount_inr, p.status, p.receipt, c.creator_handle
    FROM payments p LEFT JOIN creators c ON p.creator_id = c.id
    ORDER BY p.created_at DESC LIMIT 20
""")

if not payments_df.empty:
    display_df = payments_df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['amount_inr'] = display_df['amount_inr'] / 100.0
    
    st.dataframe(
        display_df,
        column_config={
            "payment_id": st.column_config.TextColumn("Payment ID", width="small"),
            "created_at": st.column_config.TextColumn("Date (IST)", width="small"),
            "original_currency": st.column_config.TextColumn("Currency", width="small"),
            "amount_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "receipt": st.column_config.TextColumn("Razorpay Receipt", width="medium"),
            "creator_handle": st.column_config.TextColumn("Mapped Handle", width="medium")
        },
        hide_index=True,
        width='stretch'
    )
else:
    st.warning("No payments found yet.")
