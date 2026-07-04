import os
import json
import requests
import psycopg2
from http.server import BaseHTTPRequestHandler

def get_db():
    url = os.environ.get("NEON_DATABASE_URL")
    if not url: raise Exception("Missing NEON_DATABASE_URL")
    return psycopg2.connect(url, sslmode="require")

def get_razorpay_auth():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret: raise Exception("Missing Razorpay Keys")
    return (key_id, key_secret)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            data = json.loads(body)
            
            # 🔥 FIX: Use 'skip' for pagination instead of timestamps
            skip = data.get('skip', 0)
            
            auth = get_razorpay_auth()
            conn = get_db()
            cur = conn.cursor()
            
            # 1. Fetch Currency Rates & Creators
            cur.execute("SELECT currency_code, rate_to_inr FROM currency_rates")
            rate_map = {row[0]: float(row[1]) for row in cur.fetchall()}
            
            cur.execute("SELECT id, creator_code FROM creators WHERE status = 'ACTIVE'")
            creators_map = {row[1]: str(row[0]) for row in cur.fetchall()}
            
            metrics = {"fetched": 0, "inserted": 0, "unmapped": 0, "currency_errors": 0}
            
            # 2. Fetch ONE BATCH using SKIP (The official Razorpay pagination method)
            url = f"https://api.razorpay.com/v1/payments?count=100&skip={skip}&status=captured"
            
            res = requests.get(url, auth=auth)
            if not res.ok:
                raise Exception(f"Razorpay API Error: {res.status_code} {res.text}")
            
            payments = res.json().get("items", [])
            metrics["fetched"] = len(payments)
            
            next_skip = None
            
            for p in payments:
                # A. Currency Conversion
                original_currency = p.get("currency", "INR").upper()
                rate = rate_map.get(original_currency)
                if rate is None:
                    metrics["currency_errors"] += 1
                    continue 
                
                amount_inr = int(p.get("amount", 0) * rate)
                fee_inr = p.get("fee", 0) 
                tax_inr = p.get("tax", 0)
                
                # B. Creator Mapping
                creator_id = None
                receipt = ""
                
                if p.get("order_id"):
                    o_res = requests.get(f"https://api.razorpay.com/v1/orders/{p['order_id']}", auth=auth)
                    if o_res.ok:
                        order_data = o_res.json()
                        receipt = order_data.get("receipt", "")
                        for code, cid in creators_map.items():
                            if receipt == code or receipt.startswith(f"{code}_"):
                                creator_id = cid
                                break
                
                if not creator_id and receipt:
                    metrics["unmapped"] += 1
                
                # C. Monotonic Upsert
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
            
            conn.commit()
            cur.close()
            conn.close()
            
            # 🔥 FIX: If we got exactly 100, there might be more. Return the next skip value.
            if len(payments) == 100:
                next_skip = skip + 100
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "metrics": metrics,
                "next_skip": next_skip
            }).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())
