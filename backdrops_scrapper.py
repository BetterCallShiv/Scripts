##########################################################################
#   Script: Backdrops Walls Scrapper
#   Author: @BetterCallShiv
#   Features: 
#       - Dumps complete wallpapers from Backdrops in Highest Quality.
#       - Automatically sorts files into Free/Premium and specific sub-category folders.
#   How to Use:
#       1. Install the required package: pip install requests
#       2. Run the script in your terminal: python backdrops_scrapper.py
#       3. Check the "Backdrops_Dumps" folder for your walls.
##########################################################################

import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time

api = "https://www.backdrops.io/walls/api_v3.2.php?task=all_walls"

headers = {
    "User-Agent": "okhttp/5.1.0"
}


# ================= CONFIG =================
MAX_WORKERS = 15
OUTPUT_DIR = "Backdrops_Dumps"
downloaded_count = 0
failed_count = 0
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1
RETRY_BACKOFF_MULTIPLIER = 2
progress_lock = Lock()


def create_folder_structure():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "Free"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "Premium"), exist_ok=True)


def get_category_folder(category, is_premium):
    premium_type = "Premium" if is_premium else "Free"
    category_folder = os.path.join(OUTPUT_DIR, premium_type, category)
    os.makedirs(category_folder, exist_ok=True)
    return category_folder


def download_file(item):
    global downloaded_count, failed_count
    filename = item["url"]
    category = item.get("category", "Uncategorized")
    is_premium = item.get("category_premium", "0") == "1"
    img_url = "https://www.backdrops.io/walls/upload/" + filename
    retry_delay = INITIAL_RETRY_DELAY
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(img_url, headers=headers, timeout=10)
            response.raise_for_status()
            category_folder = get_category_folder(category, is_premium)
            filepath = os.path.join(category_folder, filename)
            with open(filepath, "wb") as f:
                f.write(response.content)
            with progress_lock:
                downloaded_count += 1
                premium_label = "[PREMIUM]" if is_premium else "[FREE]"
                if attempt > 0:
                    print(f"[{downloaded_count}] {premium_label} [{category}] Downloaded (retry {attempt}): {filename}")
                else:
                    print(f"[{downloaded_count}] {premium_label} [{category}] Downloaded: {filename}")
            return True
        except (requests.ConnectionError, ConnectionResetError, requests.Timeout) as e:
            if attempt < MAX_RETRIES:
                with progress_lock:
                    print(f"[RETRY] Attempt {attempt + 1}/{MAX_RETRIES} - Retrying in {retry_delay}s: {filename}")
                time.sleep(retry_delay)
                retry_delay *= RETRY_BACKOFF_MULTIPLIER
            else:
                with progress_lock:
                    failed_count += 1
                    print(f"[ERROR] Failed to download {filename} after {MAX_RETRIES} retries: {str(e)}")
                return False 
        except Exception as e:
            with progress_lock:
                failed_count += 1
                print(f"[ERROR] Failed to download {filename}: {str(e)}")
            return False


print("Fetching wallpaper list...")
r = requests.get(api, headers=headers)
data = r.json()
walls = data["wallList"]

print("Creating folder structure...")
create_folder_structure()

print(f"Starting concurrent downloads with {MAX_WORKERS} workers...")
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(download_file, item) for item in walls]
    for future in as_completed(futures):
        future.result()

print(f"\nFinished! Downloaded: {downloaded_count}, Failed: {failed_count}, Total: {len(walls)}")
