import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from playwright.sync_api import sync_playwright

BASE_URL = "https://retrostress.net"
TOKENS_FILE = "tokens.json"

BROWSER_FLAGS = [
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
git_lock = Lock()
stop_event = Event()
created_count = 0
last_git_push = 0

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

def append_and_sync_token(token, amount_needed):
    global last_git_push
    with file_lock:
        tokens = load_existing_tokens()
        if token not in tokens:
            tokens.append(token)
            with open(TOKENS_FILE, "w", encoding="utf-8") as f:
                json.dump(tokens, f, indent=2)

    # Auto push to git every 5 tokens or on completion
    now = time.time()
    if (created_count % 5 == 0 or created_count >= amount_needed) and (now - last_git_push > 10):
        with git_lock:
            try:
                subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, timeout=15)
                subprocess.run(["git", "add", TOKENS_FILE], capture_output=True, timeout=10)
                res = subprocess.run(["git", "commit", "-m", f"Auto-harvested {created_count}/{amount_needed} tokens [skip ci]"], capture_output=True, timeout=10)
                if res.returncode == 0:
                    subprocess.run(["git", "push"], capture_output=True, timeout=20)
                    last_git_push = time.time()
            except Exception:
                pass

    return len(load_existing_tokens())

def worker_loop(worker_id, amount_needed):
    global created_count
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=BROWSER_FLAGS
        )
        try:
            ua = browser.version
            user_agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ua} Safari/537.36"
            context = browser.new_context(user_agent=user_agent)
            
            while not stop_event.is_set():
                with counter_lock:
                    if created_count >= amount_needed:
                        stop_event.set()
                        break

                try:
                    page = context.new_page()
                    # Do not block stylesheet or scripts so turnstile iframe initializes properly
                    page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "media", "font"] else r.continue_())
                    page.goto(f"{BASE_URL}/register", wait_until="domcontentloaded", timeout=25000)
                    btn = page.locator("#register-submit")

                    # Wait up to 20 seconds for turnstile solve
                    for _ in range(40):
                        if stop_event.is_set():
                            break
                        page.wait_for_timeout(500)
                        if not btn.is_disabled():
                            btn.click()
                            page.wait_for_timeout(800)
                            key = page.locator("#generated-key").input_value(timeout=3000)
                            if key and key.startswith("usr_"):
                                with counter_lock:
                                    if created_count < amount_needed:
                                        created_count += 1
                                        total = append_and_sync_token(key, amount_needed)
                                        print(f"[+] Added ({created_count}/{amount_needed}) -> {key} (Total pool: {total})", flush=True)
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
                    time.sleep(1)
        finally:
            try:
                browser.close()
            except Exception:
                pass

def main():
    add_amount = 50
    concurrency = 6

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

    # Final force push
    append_and_sync_token("", 0)

    final_pool = len(load_existing_tokens())
    print(f"\n[+] Finished. Total tokens in pool: {final_pool} (Saved & pushed to repo)", flush=True)

if __name__ == "__main__":
    main()
