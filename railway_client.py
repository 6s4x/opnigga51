import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

TOKENS_FILE = "tokens.json"
file_lock = Lock()

def load_existing_tokens():
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if isinstance(data, list):
                        return list(dict.fromkeys(data))
        except Exception:
            pass
    return []

def append_token(token):
    with file_lock:
        tokens = load_existing_tokens()
        if token not in tokens:
            tokens.append(token)
            with open(TOKENS_FILE, "w", encoding="utf-8") as f:
                json.dump(tokens, f, indent=2)
        return len(tokens)

def fetch_from_cloud(api_base_url):
    try:
        url = f"{api_base_url.rstrip('/')}/token"
        req = urllib.request.Request(url, headers={"User-Agent": "Starc-Client/1.0"})
        with urllib.request.urlopen(req, timeout=35) as res:
            data = json.loads(res.read().decode())
            if data.get("success"):
                return data.get("token")
    except Exception:
        pass
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python railway_client.py <RAILWAY_URL> [amount] [concurrency]")
        print("Example: python railway_client.py https://my-harvester.up.railway.app 100 5")
        return

    api_url = sys.argv[1]
    amount = 50
    concurrency = 5

    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        amount = int(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3].isdigit():
        concurrency = int(sys.argv[3])

    existing = load_existing_tokens()
    print("[*] Cloud Token Harvester Client (0% Host CPU / RAM)", flush=True)
    print(f"[*] Target Endpoint : {api_url}", flush=True)
    print(f"[*] Amount to ADD   : +{amount}", flush=True)
    print(f"[*] Concurrency     : {concurrency}", flush=True)
    print(f"[*] Current Pool    : {len(existing)} token(s)\n", flush=True)

    created = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        while created < amount:
            batch_size = min(concurrency, amount - created)
            futures = [executor.submit(fetch_from_cloud, api_url) for _ in range(batch_size)]
            for f in futures:
                tok = f.result()
                if tok:
                    created += 1
                    total = append_token(tok)
                    print(f"[+] Harvested ({created}/{amount}) -> {tok} (Total: {total})", flush=True)
                else:
                    print("[!] Retrying cloud challenge...", flush=True)
            time.sleep(0.5)

    final_pool = len(load_existing_tokens())
    print(f"\n[+] Finished. Total tokens in pool: {final_pool} (Saved to {TOKENS_FILE})", flush=True)

if __name__ == "__main__":
    main()
