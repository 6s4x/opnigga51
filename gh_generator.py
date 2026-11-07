import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from playwright.sync_api import sync_playwright

BASE_URL = "https://retrostress.net"
TOKENS_FILE = "tokens.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

OPTIMIZED_FLAGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-breakpad",
    "--disable-domain-reliability",
    "--mute-audio",
    "--no-default-browser-check",
    "--no-first-run",
    "--js-flags=--max-old-space-size=64"
]

file_lock = Lock()
counter_lock = Lock()
stop_event = Event()
created_count = 0

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

def worker_loop(worker_id, amount_needed):
    global created_count
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=OPTIMIZED_FLAGS
        )
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            while not stop_event.is_set():
                with counter_lock:
                    if created_count >= amount_needed:
                        stop_event.set()
                        break

                try:
                    page = context.new_page()
                    page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font", "stylesheet"] else r.continue_())
                    page.goto(f"{BASE_URL}/register", wait_until="domcontentloaded", timeout=20000)
                    btn = page.locator("#register-submit")

                    for _ in range(20):
                        if stop_event.is_set():
                            break
                        page.wait_for_timeout(400)
                        if not btn.is_disabled():
                            btn.click()
                            page.wait_for_timeout(700)
                            key = page.locator("#generated-key").input_value(timeout=3000)
                            if key and key.startswith("usr_"):
                                with counter_lock:
                                    if created_count < amount_needed:
                                        created_count += 1
                                        total = append_token(key)
                                        print(f"[+] Added ({created_count}/{amount_needed}) -> {key} (Total: {total})", flush=True)
                                        if created_count >= amount_needed:
                                            stop_event.set()
                                break
                    page.close()
                except Exception:
                    try:
                        page.close()
                    except Exception:
                        pass
                    if stop_event.is_set():
                        break
                    time.sleep(0.5)
        finally:
            try:
                browser.close()
            except Exception:
                pass

def main():
    add_amount = 50
    concurrency = 8

    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        add_amount = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        concurrency = int(sys.argv[2])

    existing = load_existing_tokens()
    current_pool = len(existing)

    print("[*] GitHub Cloud Harvester Starting...", flush=True)
    print(f"[*] Amount to ADD  : +{add_amount}", flush=True)
    print(f"[*] Active Workers : {concurrency}", flush=True)
    print(f"[*] Current Pool   : {current_pool} token(s)", flush=True)
    print(f"[*] Expected Total : {current_pool + add_amount} token(s)\n", flush=True)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker_loop, i, add_amount) for i in range(concurrency)]
        for f in futures:
            f.result()

    final_pool = len(load_existing_tokens())
    print(f"\n[+] Finished. Total tokens in pool: {final_pool} (Saved to {TOKENS_FILE})", flush=True)

if __name__ == "__main__":
    main()
