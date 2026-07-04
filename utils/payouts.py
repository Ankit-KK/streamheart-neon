from utils.db import execute_transaction
import datetime

def process_payout(
    creator_id: str, 
    gross_inr: int, 
    refunds_inr: int, 
    payout_rate: float, 
    net_payout_inr: int, 
    reference: str, 
    method: str, 
    notes: str,
    period_start: datetime.date,
    period_end: datetime.date
):
    """
    Atomically records the payout for a specific period and updates the ledger's 'paid out' tracker.
    """
    # 1. Insert into history with dates
    query1 = """
        INSERT INTO payout_history (
            creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, 
            transaction_reference, payment_method, notes, status,
            period_start, period_end
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'COMPLETED', %s, %s)
    """
    params1 = (creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, reference, method, notes, period_start, period_end)
    
    # 2. Increment the 'total_paid_out' tracker in the ledger
    # We DO NOT zero out the ledger. We just record that this much has been paid.
    query2 = """
        UPDATE creator_ledger 
        SET total_paid_out_inr = total_paid_out_inr + %s, updated_at = NOW()
        WHERE creator_id = %s
    """
    params2 = (net_payout_inr, creator_id)
    
    return execute_transaction([(query1, params1), (query2, params2)])
