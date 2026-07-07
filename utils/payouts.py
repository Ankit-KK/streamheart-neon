from utils.db import execute_transaction, run_query
import datetime

def generate_payout(creator_id: str, gross_inr: int, refunds_inr: int, payout_rate: float, net_payout_inr: int, period_start, period_end):
    """
    Step 1: Generates and locks the payout. 
    Returns True if locked, False if it was a duplicate.
    """
    try:
        query = """
            INSERT INTO payout_history (
                creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, 
                period_start, period_end, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'GENERATED')
        """
        run_query(query, (creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, period_start, period_end))
        return True # Successfully locked!
        
    except Exception as e:
        # If the database throws a "duplicate key" error, it means it already exists.
        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
            return False # Skipped because it exists
        else:
            # If it's a different error, we need to know!
            raise e 

def mark_as_paid(payout_id: str, reference: str, method: str):
    """
    Step 2: Marks the payout as paid, records the UTR, and FINALLY updates the creator's ledger.
    """
    payout_data = run_query("SELECT creator_id, net_payout_inr FROM payout_history WHERE id = %s AND status = 'GENERATED'", (payout_id,))
    if payout_data.empty:
        return False
        
    creator_id = str(payout_data.iloc[0]['creator_id'])
    net_payout = int(payout_data.iloc[0]['net_payout_inr'])

    query1 = """
        UPDATE payout_history 
        SET status = 'PAID', transaction_reference = %s, payment_method = %s, processed_at = NOW()
        WHERE id = %s
    """
    
    query2 = """
        UPDATE creator_ledger 
        SET total_paid_out_inr = total_paid_out_inr + %s, updated_at = NOW()
        WHERE creator_id = %s
    """
    
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
