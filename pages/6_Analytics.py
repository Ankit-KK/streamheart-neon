import streamlit as st
import pandas as pd
import datetime
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

st.set_page_config(page_title="Analytics", layout="wide")
st.title("📊 Global Command Dashboard")
st.caption("Real-time platform analytics, financial health, and system alerts.")

# ==============================================================================
# 2. DATE RANGE SELECTOR (SIDEBAR)
# ==============================================================================
st.sidebar.header("📅 Analytics Period")
period_option = st.sidebar.selectbox(
    "Quick Select", 
    ["Today", "Yesterday", "This Week", "Last Week", "This Month", "Last Month", "Custom"]
)

# 🔥 FIX: Force "today" to be calculated in IST, not server UTC
ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = datetime.datetime.now(ist_tz).date()

if period_option == "Today":
    start_date, end_date = today, today
elif period_option == "Yesterday":
    start_date, end_date = today - datetime.timedelta(days=1), today - datetime.timedelta(days=1)
elif period_option == "This Week":
    start_date = today - datetime.timedelta(days=today.weekday())
    end_date = today
elif period_option == "Last Week":
    end_date = today - datetime.timedelta(days=today.weekday() + 1)
    start_date = end_date - datetime.timedelta(days=6)
elif period_option == "This Month":
    start_date = today.replace(day=1)
    end_date = today
elif period_option == "Last Month":
    end_date = today.replace(day=1) - datetime.timedelta(days=1)
    start_date = end_date.replace(day=1)
else: # Custom
    default_start = today - datetime.timedelta(days=30)
    start_date, end_date = st.sidebar.date_input("Custom Range", value=(default_start, today))

st.sidebar.success(f"📅 Analyzing: **{start_date}** to **{end_date}**")

# Calculate previous period for deltas (e.g., if viewing 7 days, compare to the 7 days before that)
delta_days = (end_date - start_date).days + 1
prev_end = start_date - datetime.timedelta(days=1)
prev_start = prev_end - datetime.timedelta(days=delta_days - 1)

# ==============================================================================
# 3. KPI CALCULATIONS
# ==============================================================================
def get_kpis(s_date, e_date):
    query = """
        SELECT 
            COUNT(*) as total_transactions,
            COALESCE(SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END), 0) as total_gross_paise,
            COALESCE(SUM(CASE WHEN status = 'captured' THEN fee_inr ELSE 0 END), 0) as total_fees_paise,
            COALESCE(SUM(CASE WHEN status = 'captured' THEN tax_inr ELSE 0 END), 0) as total_tax_paise
        FROM payments
        WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
    """
    df = run_query(query, (s_date, e_date))
    if df.empty:
        return {"transactions": 0, "gross": 0.0, "fees": 0.0, "tax": 0.0, "aov": 0.0}
    
    row = df.iloc[0]
    gross = int(pd.to_numeric(row['total_gross_paise'], errors='coerce') or 0) / 100.0
    transactions = int(pd.to_numeric(row['total_transactions'], errors='coerce') or 0)
    fees = int(pd.to_numeric(row['total_fees_paise'], errors='coerce') or 0) / 100.0
    tax = int(pd.to_numeric(row['total_tax_paise'], errors='coerce') or 0) / 100.0
    aov = gross / transactions if transactions > 0 else 0.0
    
    return {
        "transactions": transactions,
        "gross": gross,
        "fees": fees,
        "tax": tax,
        "aov": aov
    }

current_kpis = get_kpis(start_date, end_date)
prev_kpis = get_kpis(prev_start, prev_end)

def calc_delta(current, previous):
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return ((current - previous) / previous) * 100.0

# ==============================================================================
# 4. UI: KPI CARDS
# ==============================================================================
st.subheader("🚀 Platform Performance")
c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Total Gross Collected", 
    f"₹{current_kpis['gross']:,.2f}", 
    f"{calc_delta(current_kpis['gross'], prev_kpis['gross']):.1f}%"
)
c2.metric(
    "Net Platform Revenue", 
    f"₹{(current_kpis['fees'] + current_kpis['tax']):,.2f}", 
    f"{calc_delta(current_kpis['fees'] + current_kpis['tax'], prev_kpis['fees'] + prev_kpis['tax']):.1f}%"
)
c3.metric(
    "Average Order Value (AOV)", 
    f"₹{current_kpis['aov']:,.2f}", 
    f"{calc_delta(current_kpis['aov'], prev_kpis['aov']):.1f}%"
)
c4.metric(
    "Total Transactions", 
    f"{current_kpis['transactions']:,}", 
    f"{calc_delta(current_kpis['transactions'], prev_kpis['transactions']):.1f}%"
)

st.divider()

# ==============================================================================
# 5. UI: DAILY TREND
# ==============================================================================
st.subheader("📈 Daily Collection Trend")
trend_df = run_query("""
    SELECT 
        (created_at AT TIME ZONE 'Asia/Kolkata')::date as day,
        SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END) / 100.0 as gross_inr
    FROM payments
    WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
    GROUP BY day
    ORDER BY day
""", (start_date, end_date))

if not trend_df.empty:
    chart_df = trend_df.copy()
    chart_df['gross_inr'] = pd.to_numeric(chart_df['gross_inr'], errors='coerce').fillna(0)
    st.line_chart(chart_df.set_index('day')['gross_inr'])
else:
    st.info("No data for this period.")

st.divider()

# ==============================================================================
# 6. UI: DEEP DIVE
# ==============================================================================
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💱 Currency Breakdown")
    currency_df = run_query("""
        SELECT 
            original_currency,
            COUNT(*) as volume,
            SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END) / 100.0 as gross_inr
        FROM payments
        WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
        GROUP BY original_currency
        ORDER BY gross_inr DESC
    """, (start_date, end_date))
    
    if not currency_df.empty:
        display_curr = currency_df.copy()
        display_curr['gross_inr'] = pd.to_numeric(display_curr['gross_inr'], errors='coerce').fillna(0)
        st.dataframe(
            display_curr,
            column_config={
                "original_currency": "Currency",
                "volume": "Volume",
                "gross_inr": st.column_config.NumberColumn("Gross (₹)", format="%.2f")
            },
            hide_index=True,
            width='stretch'
        )
    else:
        st.info("No currency data.")

with col_right:
    st.subheader("🏆 Top Creators (By Revenue)")
    creators_df = run_query("""
        SELECT 
            c.creator_handle,
            COUNT(p.payment_id) as volume,
            SUM(CASE WHEN p.status = 'captured' THEN p.amount_inr ELSE 0 END) / 100.0 as gross_inr
        FROM payments p
        JOIN creators c ON p.creator_id = c.id
        WHERE (p.created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
        GROUP BY c.creator_handle
        ORDER BY gross_inr DESC
        LIMIT 10
    """, (start_date, end_date))
    
    if not creators_df.empty:
        display_creators = creators_df.copy()
        display_creators['gross_inr'] = pd.to_numeric(display_creators['gross_inr'], errors='coerce').fillna(0)
        st.dataframe(
            display_creators,
            column_config={
                "creator_handle": "Creator",
                "volume": "Transactions",
                "gross_inr": st.column_config.NumberColumn("Gross (₹)", format="%.2f")
            },
            hide_index=True,
            width='stretch'
        )
    else:
        st.info("No creator data.")

st.divider()

# ==============================================================================
# 7. UI: SYSTEM HEALTH
# ==============================================================================
st.subheader("🚨 System Health & Alerts")
unmapped_df = run_query("SELECT COUNT(*) as count FROM payments WHERE creator_id IS NULL")
unmapped_count = int(pd.to_numeric(unmapped_df.iloc[0]['count'], errors='coerce') or 0) if not unmapped_df.empty else 0

if unmapped_count > 0:
    st.warning(f"⚠️ **{unmapped_count} Unmapped Payments:** Go to '4_Sync' and run the Re-map engine or add missing creators.")
else:
    st.success("✅ All payments are successfully mapped to creators.")
