import os
import json
import requests
import psycopg2
from http.server import BaseHTTPRequestHandler

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_db():
    url = os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise Exception("Missing NEON_DATABASE_URL")
    return psycopg2.connect(url, sslmode="require")

def get_razorpay_auth():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise Exception("Missing Razorpay Keys")
    return (key_id, key_secret)

# ==========================================
# VERCEL SERVERLESS HANDLER
# ==========================================
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read incoming request (if any payload was sent)
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            data = json.loads(body)
            
            # Optional: Allow forcing a specific start time, otherwise start from NOW
            to_timestamp = data.get('to_timestamp', None) 
            
            auth = get_razorpay_auth()
            conn = get_db()
            cur = conn.cursor()
            
            # 1. Fetch Currency Rates from Neon (Prevents the 1.0 fallback bug)
            cur.execute("SELECT currency_code, rate_to_inr FROM currency_rates")
            rate_map = {row[0]: float(row[1]) for row in cur.fetchall()}
            
            # 2. Fetch Creators for O(1) Mapping
            cur.execute("SELECT id, creator_code FROM creators WHERE status = 'ACTIVE'")
            creators_map = {row[1]: str(row[0]) for row in cur.fetchall()}
            
            metrics = {"fetched": 0, "inserted": 0, "unmapped": 0, "currency_errors": 0}
            
            # 3. Paginate through Razorpay Payments (Stable Cursor)
            count = 100
            while True:
                url = f"https://api.razorpay.com/v1/payments?count={count}&status=captured"
                if to_timestamp:
                    url += f"&to={to_timestamp}"
                
                res = requests.get(url, auth=auth)
                if not res.ok:
                    raise Exception(f"Razorpay API Error: {res.status_code} {res.text}")
                
                payments = res.json().get("items", [])
                if not payments:
                    break
                
                metrics["fetched"] += len(payments)
                
                for p in payments:
                    # A. Currency Conversion
                    original_currency = p.get("currency", "INR").upper()
                    rate = rate_map.get(original_currency)
                    
                    if rate is None:
                        metrics["currency_errors"] += 1
                        continue # Skip if we don't have the exchange rate, prevents bad math
                    
                    amount_inr = int(p.get("amount", 0) * rate)
                    fee_inr = p.get("fee", 0) # Razorpay fees are always in INR paise
                    tax_inr = p.get("tax", 0)
                    
                    # B. Creator Mapping (via Order Receipt)
                    creator_id = None
                    receipt = ""
                    
                    if p.get("order_id"):
                        # Fetch order to get the receipt
                        o_res = requests.get(f"https://api.razorpay.com/v1/orders/{p['order_id']}", auth=auth)
                        if o_res.ok:
                            order_data = o_res.json()
                            receipt = order_data.get("receipt", "")
                            
                            # Exact prefix match to prevent "abc" stealing "abc_pro"
                            for code, cid in creators_map.items():
                                if receipt == code or receipt.startswith(f"{code}_"):
                                    creator_id = cid
                                    break
                    
                    if not creator_id and receipt:
                        metrics["unmapped"] += 1
                    
                    # C. The Monotonic Upsert (The Magic)
                    # We use COALESCE(payments.creator_id, EXCLUDED.creator_id) for the mapping.
                    # This means: "If the DB already has a creator_id, KEEP IT. If it's NULL, use the new one."
                    # This guarantees a sync can NEVER overwrite a manual mapping with NULL.
                    cur.execute("""
                        INSERT INTO payments (
                            payment_id, order_id, creator_id, original_currency, original_amount, 
                            amount_inr, fee_inr, tax_inr, status, method, email, contact, 
                            receipt, creator_code_attempted, created_at, raw_payment_payload
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s
                        )
                        ON CONFLICT (payment_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            fee_inr = EXCLUDED.fee_inr,
                            tax_inr = EXCLUDED.tax_inr,
                            amount_inr = EXCLUDED.amount_inr,
                            -- MONOTONIC MAPPING: Never clobber an existing creator_id with NULL
                            creator_id = COALESCE(payments.creator_id, EXCLUDED.creator_id),
                            creator_code_attempted = COALESCE(NULLIF(payments.creator_code_attempted, ''), EXCLUDED.creator_code_attempted)
                    """, (
                        p["id"], p.get("order_id"), creator_id, original_currency, p.get("amount"),
                        amount_inr, fee_inr, tax_inr, p["status"], p.get("method"), 
                        p.get("email"), p.get("contact"), receipt, 
                        receipt.split('_')[0] if receipt and '_' in receipt else None,
                        p["created_at"], json.dumps(p)
                    ))
                    metrics["inserted"] += 1
                
                # Move cursor to the oldest payment in this batch
                to_timestamp = payments[-1]["created_at"]
                
                # Stop if we got less than batch size (end of data)
                if len(payments) < count:
                    break
            
            conn.commit()
            cur.close()
            conn.close()
            
            # Return success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "metrics": metrics}).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())
