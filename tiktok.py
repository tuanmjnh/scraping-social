import time
import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# ==========================
# Cấu hình Hệ thống
# ==========================
interval_loop = 15  # Số giây thực hiện check lại
is_headless = True

# ==========================
# Cấu hình Tiktok
# ==========================
tiktok_user = 'huynhhuyhoang_official'  # Tài khoản tiktok cần check
include_pinned = False  # lấy video được pinne
file_new_videos = 'new_videos.txt'  # File log lưu video mới
file_old_videos = 'old_videos.txt'  # File log lưu video cũ

# ==========================
# Cấu hình Youtube
# ==========================

# ==========================
# Cấu hình Telegram
# ==========================
TELEGRAM_BOT_TOKEN = "8434126925:AAHcuvLkscCyMm6PNKOeNCtZdp5w7sI3AiI"  # Token bot telegram
TELEGRAM_CHAT_ID = "@TMScrapingTest"      # ID group chat


def send_telegram_message(text: str):
    """Gửi tin nhắn đến nhóm Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
        print("✅ Đã gửi thông báo Telegram")
    except Exception as e:
        print("❌ Lỗi gửi Telegram:", e)


def extract_video_links(source, pinned: bool = False):
    video_links = []
    for a in source.find_all("a"):
        href = a.get("href")
        if not href or "/video/" not in href:
            continue

        # Kiểm tra pinned (chỉ text)
        pinned_badge = a.find(string=lambda text: text and text.strip() == "Pinned")
        is_pinned = pinned_badge is not None

        if pinned or not is_pinned:
            video_links.append(href)

    return video_links


def get_videos_data(username: str, pinned: bool = False, headless: bool = True):
    """Lấy danh sách video từ TikTok profile"""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    url = f"https://www.tiktok.com/@{username}"
    driver.get(url)
    time.sleep(5)  # chờ JS load

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    return extract_video_links(soup, pinned)


def load_videos(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_videos(links, file_path):
    with open(file_path, "w", encoding="utf-8") as f:  # a
        f.write("\n".join(links))


def monitor_new_videos(username: str, interval: int = 15, pinned: bool = False, headless: bool = True):
    """Liên tục kiểm tra video mới, ghi log ra file và gửi Telegram"""
    seen_videos = load_videos(file_old_videos)
    print(f"📂 Đã load {len(seen_videos)} video từ {file_old_videos}")

    while True:
        print("\n🔄 Kiểm tra video mới...")
        current_videos = set(get_videos_data(username, pinned, headless))
        new_videos = current_videos - seen_videos

        if new_videos:
            print(f"🚀 Phát hiện {len(new_videos)} video mới!")
            txt_new_videos = "\n".join(new_videos)
            print(txt_new_videos)
            # for link in new_videos:
            #     print(link)
                # Ghi log
                # log_new_videos([link], file_new_videos)
                # Gửi thông báo Telegram
                # send_telegram_message(f"🎬 Video mới từ @{username}:\n{link}")
            # Ghi log
            save_videos(new_videos, file_new_videos)
            # Gửi thông báo Telegram
            send_telegram_message(f"🎬 Video mới từ @{username}:\n{txt_new_videos}")
            # Cập nhật old
            seen_videos |= new_videos
            save_videos(seen_videos, file_old_videos)
        else:
            print("Không có video mới.")

        time.sleep(interval)


# ==========================
# Ví dụ sử dụng
# ==========================
if __name__ == "__main__":
    monitor_new_videos(tiktok_user, interval_loop, include_pinned, is_headless)  # kiểm tra mỗi 15s