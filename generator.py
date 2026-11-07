import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from playwright.sync_api import sync_playwright

BASE_URL = "https://retrostress.net"
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
TOKENS_FILE = "tokens.json"

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--window-position=-3200,-3200",
    "--window-size=600,400",
    "--mute-audio",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-breakpad",
    "--disable-domain-reliability",
    "--no-first-run",
    "--no-default-browser-check",
    "--js-flags=--max-old-space-size=48"
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

def worker_routine(worker_id, amount_needed):
    global created_count
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=BRAVE_PATH,
            headless=False,
            args=BROWSER_ARGS
        )
        try:
            page = browser.new_page()
            page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())

            while not stop_event.is_set():
                with counter_lock:
                    if created_count >= amount_needed:
                        stop_event.set()
                        break

                try:
                    t_start = time.time()
                    page.goto(f"{BASE_URL}/register", wait_until="domcontentloaded", timeout=12000)
                    btn = page.locator("#register-submit")

                    # Turnstile completes in 2.5 - 3.5s
                    for _ in range(16):
                        if stop_event.is_set():
                            break
                        page.wait_for_timeout(250)
                        if not btn.is_disabled():
                            btn.click()
                            page.wait_for_timeout(400)
                            key = page.locator("#generated-key").input_value(timeout=2000)
                            if key and key.startswith("usr_"):
                                with counter_lock:
                                    if created_count < amount_needed:
                                        created_count += 1
                                        total = append_token(key)
                                        elapsed = round(time.time() - t_start, 2)
                                        print(f"[+] [W{worker_id}] {key} ({created_count}/{amount_needed} | {elapsed}s | Pool: {total})", flush=True)
                                        if created_count >= amount_needed:
                                            stop_event.set()
                                break
                except Exception:
                    if stop_event.is_set():
                        break
                    time.sleep(0.3)

            try:
                page.close()
            except Exception:
                pass
        finally:
            try:
                browser.close()
            except Exception:
                pass

def main():
    add_amount = 50
    concurrency = 4

    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        add_amount = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        concurrency = int(sys.argv[2])

    existing = load_existing_tokens()
    current_pool = len(existing)

    print("[*] Starc Turbo Engine (Offscreen Native Fast-Solve)", flush=True)
    print(f"[*] Amount to ADD  : +{add_amount}", flush=True)
    print(f"[*] Active Workers : {concurrency}", flush=True)
    print(f"[*] Current Pool   : {current_pool} token(s)", flush=True)
    print(f"[*] Target Pool    : {current_pool + add_amount} token(s)\n", flush=True)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker_routine, i + 1, add_amount) for i in range(concurrency)]
        for f in futures:
            f.result()

    final_pool = len(load_existing_tokens())
    print(f"\n[+] Finished. Added {created_count} tokens. Total pool: {final_pool} (Saved to {TOKENS_FILE})", flush=True)

if __name__ == "__main__":
    main()
