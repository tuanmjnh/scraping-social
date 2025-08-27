import time
import os
import requests
import threading
import xml.etree.ElementTree as ET
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from typing import Optional

# ==========================
# Đọc config từ file
# ==========================


def load_config(file_path="config.txt") -> dict:
    config = {}
    if not os.path.exists(file_path):
        print(f"⚠️ Không tìm thấy {file_path}, dùng cấu hình mặc định.")
        return config
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    return config


def get_bool(value: str, default=False) -> bool:
    return value.lower() in ["1", "true", "yes", "y"] if isinstance(value, str) else default


# ==========================
# Load cấu hình
# ==========================
config = load_config("config.txt")

interval_loop = int(config.get("interval_tiktok", 60))
interval_youtube = int(config.get("interval_youtube", 60))
initial_delay_global = int(config.get("initial_delay", 6))
send_delay_global = int(config.get("send_delay", 6))
max_videos_check = int(config.get("max_videos", 5))
is_headless = get_bool(config.get("headless", "True"))
timeout_load = int(config.get("timeout_load", 30))

TELEGRAM_BOT_TOKEN = config.get("telegram_token", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = config.get("telegram_chat", "@YOUR_CHANNEL")
disable_web_page_preview = get_bool(config.get("disable_web_page_preview", "False"))

channel_tiktok_file = config.get("tiktok_file", "channel_tiktok.txt")
channel_youtube_file = config.get("youtube_file", "channel_youtube.txt")

# ==========================
# Thư mục logs
# ==========================
logs_dir = "logs"
os.makedirs(logs_dir, exist_ok=True)


# ==========================
# Hàm hỗ trợ
# ==========================
def send_telegram_message(text: str):
    time.sleep(send_delay_global)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": disable_web_page_preview}
    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
        print("✅ Đã gửi thông báo Telegram")
    except Exception as e:
        print("❌ Lỗi gửi Telegram:", e)


def load_videos(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_videos(links, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(links)))


# ==========================
# TikTok
# ==========================
def extract_video_links(source, pinned: bool = False):
    video_links = []
    for a in source.find_all("a"):
        href = a.get("href")
        if not href or "/video/" not in href:
            continue
        pinned_badge = a.find(string=lambda text: text and text.strip() == "Pinned")
        is_pinned = pinned_badge is not None
        if pinned or not is_pinned:
            video_links.append(href)
    return video_links[:max_videos_check]


def normalize_tiktok_username(input_str: str) -> str:
    url = input_str.strip()
    if url.startswith("http"):
        parts = url.rstrip('/').split('/')
        username = parts[-1]
        if username.startswith('@'):
            username = username[1:]
        return username
    else:
        if url.startswith('@'):
            return url[1:]
        return url


def get_tiktok_videos(username: str, pinned: bool = False, headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(timeout_load)  # timeout load trang
    driver.set_script_timeout(timeout_load)     # timeout script
    url = f"https://www.tiktok.com/@{username}"
    try:
        driver.get(url)
        time.sleep(5)
    except Exception as e:
        print(f"❌ Lỗi load TikTok {username}: {e}")
        driver.quit()
        return []
    # driver.get(url)
    time.sleep(5)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    return extract_video_links(soup, pinned)


def monitor_tiktok(username_input: str, interval: int = 15, pinned: bool = False, headless: bool = True, initial_delay: int = 0):
    if initial_delay:
        time.sleep(initial_delay)

    username = normalize_tiktok_username(username_input)
    file_old = os.path.join(logs_dir, f"tiktok_old_{username}.txt")
    file_new = os.path.join(logs_dir, f"tiktok_new_{username}.txt")

    seen_videos = load_videos(file_old)
    print(f"📂 TikTok @{username}: đã load {len(seen_videos)} video")

    next_run = time.time()
    while True:
        try:
            current_videos = set(get_tiktok_videos(username, pinned, headless))
            new_videos = list(current_videos - seen_videos)[:max_videos_check]

            if new_videos:
                for link in new_videos:
                    msg = f"🎬 TikTok mới từ @{username}: {link}"
                    print(msg)
                    send_telegram_message(msg)
                save_videos(seen_videos | set(new_videos), file_new)
                seen_videos |= set(new_videos)
                save_videos(seen_videos, file_old)
        except Exception as e:
            print(f"❌ Lỗi TikTok @{username}:", e)

        next_run += interval
        sleep_for = max(0, next_run - time.time())
        time.sleep(sleep_for)


# ==========================
# YouTube
# ==========================
def _extract_channel_id_from_text(text: str) -> Optional[str]:
    markers = ['"channelId":"UC', '"externalId":"UC', '"browseId":"UC', '/channel/UC']
    for mk in markers:
        idx = text.find(mk)
        if idx != -1:
            start = text.find('UC', idx)
            if start == -1:
                continue
            end = start
            allowed = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
            while end < len(text) and text[end] in allowed:
                end += 1
            cid = text[start:end]
            if cid.startswith('UC') and len(cid) >= 24:
                return cid
    return None


def get_channel_id_from_url(url: str) -> Optional[str]:
    try:
        if url.startswith('@'):
            url = f"https://www.youtube.com/{url}"
        elif url.startswith('UC'):
            return url

        if '/channel/UC' in url:
            return url.split('/channel/')[-1].split('/')[0]

        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        for sfx in ['', '/about', '/videos']:
            u = url.rstrip('/') + sfx
            u = u + ('&hl=en' if '?' in u else '?hl=en')
            r = requests.get(u, headers=headers, timeout=20)
            r.raise_for_status()

            if '/channel/UC' in r.url:
                return r.url.split('/channel/')[-1].split('/')[0]

            cid = _extract_channel_id_from_text(r.text)
            if cid:
                return cid
    except Exception as e:
        print('❌ Lỗi lấy channel_id (requests):', e)

    try:
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/120.0.0.0 Safari/537.36")
        options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(timeout_load)  # timeout load trang
        driver.set_script_timeout(timeout_load)     # timeout script
        try:
            driver.get(url)
            time.sleep(5)
        except Exception as e:
            print(f"❌ Lỗi load channel_id {url}: {e}")
            driver.quit()
        # driver.get(url)
        time.sleep(4)
        html = driver.page_source
        driver.quit()
        cid = _extract_channel_id_from_text(html)
        if cid:
            return cid
    except Exception as e:
        print('❌ Lỗi lấy channel_id (selenium):', e)

    return None


def get_youtube_videos(channel_id: str):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    r = requests.get(url)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    videos = []
    for entry in root.findall("atom:entry", ns):
        link_elem = entry.find("atom:link", ns)
        if link_elem is not None and "href" in link_elem.attrib:
            link = link_elem.attrib["href"]
        else:
            link = None
        title_elem = entry.find("atom:title", ns)
        title = title_elem.text if title_elem is not None else ""
        if link:
            videos.append((title, link))
    return videos[:max_videos_check]


def load_youtube_channels(file_path):
    channels = []
    if not os.path.exists(file_path):
        return channels

    updated_lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) == 2:
                channels.append((parts[0], parts[1]))
                updated_lines.append(line)
            else:
                channel_url = parts[0]
                cid = get_channel_id_from_url(channel_url)
                if cid:
                    channels.append((channel_url, cid))
                    updated_lines.append(f"{channel_url} {cid}")
                else:
                    print(f"❌ Không lấy được channel_id cho {channel_url}")
                    updated_lines.append(channel_url)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(updated_lines))
    return channels


def monitor_youtube(channel_url: str, channel_id: str, interval: int = 60, initial_delay: int = 0):
    if initial_delay:
        time.sleep(initial_delay)

    # safe_name = channel_url.replace("https://", "").replace("/", "_").replace("@", "at_")
    safe_name = channel_url.replace("https://www.youtube.com/@", "").replace("/", "")
    file_old = os.path.join(logs_dir, f"youtube_old_{safe_name}_{channel_id}.txt")
    file_new = os.path.join(logs_dir, f"youtube_new_{safe_name}_{channel_id}.txt")

    seen_videos = load_videos(file_old)
    print(f"📂 YouTube {channel_url}: đã load {len(seen_videos)} video")

    next_run = time.time()
    while True:
        try:
            videos = get_youtube_videos(channel_id)
            current_videos = set(link for _, link in videos)
            new_videos = list(current_videos - seen_videos)[:max_videos_check]

            if new_videos:
                for title, link in videos:
                    if link in new_videos:
                        msg = f"📺 YouTube mới: {title} - {link}"
                        print(msg)
                        send_telegram_message(msg)
                save_videos(seen_videos | set(new_videos), file_new)
                seen_videos |= set(new_videos)
                save_videos(seen_videos, file_old)
        except Exception as e:
            print(f"❌ Lỗi YouTube {channel_url}:", e)

        next_run += interval
        sleep_for = max(0, next_run - time.time())
        time.sleep(sleep_for)


# ==========================
# Chạy nhiều channel song song
# ==========================
def load_channels(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return []


def start_monitors():
    tiktok_channels = load_channels(channel_tiktok_file)
    youtube_channels = load_youtube_channels(channel_youtube_file)

    threads = []

    for i, username in enumerate(tiktok_channels):
        t = threading.Thread(
            target=monitor_tiktok,
            args=(username, interval_loop, False, is_headless, i * initial_delay_global),
            daemon=True
        )
        t.start()
        threads.append(t)

    for j, (url, cid) in enumerate(youtube_channels):
        t = threading.Thread(
            target=monitor_youtube,
            args=(url, cid, interval_youtube, j * initial_delay_global),
            daemon=True
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    start_monitors()
