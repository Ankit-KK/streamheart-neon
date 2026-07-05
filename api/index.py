import os
import json
import requests
import psycopg2
import concurrent.futures
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

def fetch_order_receipt(order_id, auth):
    try:
        res = requests.get(f"https://api.razorpay.com/v1/orders/{order_id}", auth=auth, timeout=5)
        if res.ok:
            return order_id, res.json().get("receipt", "")
    except Exception:
        pass
    return order_id, ""

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b'{}'
            data = json.loads(body)
            
            # Accept both 'from' (forward) and 'to' (backward) timestamps
            from_timestamp = data.get('from_timestamp', None)
            to_timestamp = data.get('to_timestamp', None)
            
            auth = get_razorpay_auth()
            conn = get_db()
            cur = conn.cursor()
            
            cur.execute("SELECT currency_code, rate_to_inr FROM currency_rates")
            rate_map = {row[0]: float(row[1]) for row in cur.fetchall()}
            
            cur.execute("SELECT id, creator_code FROM creators WHERE status = 'ACTIVE'")
            creators_map = {row[1]: str(row[0]) for row in cur.fetchall()}
            
            metrics = {"fetched": 0, "inserted": 0, "unmapped": 0, "currency_errors": 0}
            
            # Build Razorpay URL
            url = f"https://api.razorpay.com/v1/payments?count=100&status=captured"
            if from_timestamp:
                url += f"&from={int(from_timestamp)}"
            if to_timestamp:
                url += f"&to={int(to_timestamp)}"
                
            res = requests.get(url, auth=auth, timeout=10)
            if not res.ok:
                raise Exception(f"Razorpay API Error: {res.status_code} {res.text}")
            
            payments = res.json().get("items", [])
            metrics["fetched"] = len(payments)
            
            if not payments:
                conn.close()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "metrics": metrics, "next_to": None}).encode())
                return

            # Fetch receipts in parallel
            order_ids = list(set([p.get("order_id") for p in payments if p.get("order_id")]))
            receipt_map = {}
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(fetch_order_receipt, oid, auth): oid for oid in order_ids}
                for future in concurrent.futures.as_completed(futures):
                    oid, receipt = future.result()
                    receipt_map[oid] = receipt
            
            # Process and Save
            for p in payments:
                original_currency = p.get("currency", "INR").upper()
                rate = rate_map.get(original_currency)
                if rate is None:
                    metrics["currency_errors"] += 1
                    continue 
                
                amount_inr = int(p.get("amount", 0) * rate)
                fee_inr = p.get("fee", 0) 
                tax_inr = p.get("tax", 0)
                
                creator_id = None
                receipt = receipt_map.get(p.get("order_id"), "")
                
                for code, cid in creators_map.items():
                    if receipt == code or receipt.startswith(f"{code}_"):
                        creator_id = cid
                        break
                
                if not creator_id and receipt:
                    metrics["unmapped"] += 1
                
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
            
            # The 'next_to' cursor is the oldest payment in the current batch.
            # This works for both Forward (from) and Backward (to) pagination.
            next_to = payments[-1]["created_at"] if len(payments) == 100 else None
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "metrics": metrics,
                "next_to": next_to
            }).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())
