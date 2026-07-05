from utils.db import execute_transaction, run_query
import datetime

def generate_payout(creator_id: str, gross_inr: int, refunds_inr: int, payout_rate: float, net_payout_inr: int, period_start: datetime.date, period_end: datetime.date):
    """
    Step 1: Generates and locks the payout. Does NOT touch the ledger.
    Returns the payout_id if successful, None if a payout for this period already exists.
    """
    # Prevent duplicate payouts for the exact same period
    existing = run_query("""
        SELECT id FROM payout_history 
        WHERE creator_id = %s AND period_start = %s AND period_end = %s 
        AND status IN ('GENERATED', 'PAID')
    """, (creator_id, period_start, period_end))
    
    if not existing.empty:
        return None 
        
    query = """
        INSERT INTO payout_history (
            creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, 
            period_start, period_end, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'GENERATED')
        RETURNING id
    """
    df = run_query(query, (creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, period_start, period_end))
    if not df.empty:
        return str(df.iloc[0]['id'])
    return None

def mark_as_paid(payout_id: str, reference: str, method: str):
    """
    Step 2: Marks the payout as paid, records the UTR, and FINALLY updates the creator's ledger.
    """
    # Get the payout details to update the ledger correctly
    payout_data = run_query("SELECT creator_id, net_payout_inr FROM payout_history WHERE id = %s AND status = 'GENERATED'", (payout_id,))
    if payout_data.empty:
        return False
        
    creator_id = str(payout_data.iloc[0]['creator_id'])
    net_payout = int(payout_data.iloc[0]['net_payout_inr'])

    # Query 1: Update payout status and UTR
    query1 = """
        UPDATE payout_history 
        SET status = 'PAID', transaction_reference = %s, payment_method = %s, processed_at = NOW()
        WHERE id = %s
    """
    
    # Query 2: Increment the 'paid out' tracker in the ledger
    query2 = """
        UPDATE creator_ledger 
        SET total_paid_out_inr = total_paid_out_inr + %s, updated_at = NOW()
        WHERE creator_id = %s
    """
    
    # Execute both in a single atomic transaction
    return execute_transaction([
        (query1, (reference, method, payout_id)),
        (query2, (net_payout, creator_id))
    ])

def rollback_payout(payout_id: str):
    """
    Emergency: Cancels a GENERATED payout. Does NOT touch the ledger.
    """
    query = "UPDATE payout_history SET status = 'CANCELLED' WHERE id = %s AND status = 'GENERATED'"
    run_query(query, (payout_id,))
    return True
