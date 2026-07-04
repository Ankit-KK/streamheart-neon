from utils.db import execute_transaction

def process_payout(creator_id: str, gross_inr: int, refunds_inr: int, payout_rate: float, net_payout_inr: int, reference: str, method: str, notes: str):
    """
    Atomically records the payout and resets the creator's ledger.
    """
    query1 = """
        INSERT INTO payout_history (
            creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, 
            transaction_reference, payment_method, notes, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'COMPLETED')
    """
    params1 = (creator_id, gross_inr, refunds_inr, payout_rate, net_payout_inr, reference, method, notes)
    
    query2 = """
        UPDATE creator_ledger 
        SET total_gross_inr = 0, total_fees_inr = 0, total_tax_inr = 0, 
            total_refunds_inr = 0, total_payments_count = 0, updated_at = NOW()
        WHERE creator_id = %s
    """
    params2 = (creator_id,)
    
    # Execute both in a single transaction
    return execute_transaction([(query1, params1), (query2, params2)])
