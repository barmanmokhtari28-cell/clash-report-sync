import os
import re
import html
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
SOURCE_CHANNEL = "clashreport"
STATE_FILE = "last_id.txt"

def get_last_processed_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                content = f.read().strip()
                if content:
                    return int(content)
        except Exception as e:
            print(f"[DEBUG] Error reading state file: {e}")
    return 0

def save_last_processed_id(last_id):
    try:
        with open(STATE_FILE, "w") as f:
            f.write(str(last_id))
        print(f"[DEBUG] Saved last_id.txt with ID: {last_id}")
    except Exception as e:
        print(f"[DEBUG] Error writing state file: {e}")

def scrape_channel():
    url = f"https://t.me/s/{SOURCE_CHANNEL}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    print(f"[DEBUG] Fetching URL: {url}")
    response = requests.get(url, headers=headers)
    print(f"[DEBUG] HTTP Status Code: {response.status_code}")

    if response.status_code != 200:
        print("[DEBUG] Failed to load the public web preview page.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    messages = soup.select(".tgme_widget_message")
    print(f"[DEBUG] Found {len(messages)} elements with class 'tgme_widget_message'")

    parsed_posts = []
    for msg_body in messages:
        data_post = msg_body.get("data-post")
        if not data_post:
            continue

        try:
            post_id = int(data_post.split("/")[-1])
        except ValueError:
            continue

        post_link = f"https://t.me/{data_post}"

        # Date extraction
        time_elem = msg_body.select_one(".tgme_widget_message_date time")
        date_str = time_elem.get("datetime") if time_elem else None

        # Text extraction (Fix line breaks & paragraph formatting)
        text_elem = msg_body.select_one(".tgme_widget_message_text")
        if text_elem:
            for br in text_elem.find_all("br"):
                br.replace_with("\n")
            text = text_elem.get_text()
        else:
            text = ""

        # Video extraction
        video_elem = msg_body.select_one("video.tgme_widget_message_video")
        video_url = video_elem.get("src") if video_elem else None

        # Photo extraction
        photo_elem = msg_body.select_one(".tgme_widget_message_photo_wrap")
        photo_url = None
        if photo_elem:
            style = photo_elem.get("style", "")
            match = re.search(r"background-image:\s*url\(['\"]?([^'\"]+)['\"]?\)", style)
            if match:
                photo_url = match.group(1)

        parsed_posts.append({
            "id": post_id,
            "link": post_link,
            "text": text.strip(),
            "date_str": date_str,
            "video_url": video_url,
            "photo_url": photo_url
        })

    return parsed_posts

def translate_to_persian(text, max_retries=3):
    """
    Translates text to Persian using Google's direct JSON endpoint (client=gtx).
    Free, unlimited, requires no API keys or proxies, and won't trigger Google's HTML error blocks.
    """
    if not text or not text.strip():
        return ""

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "fa",
        "dt": "t"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    for attempt in range(max_retries):
        try:
            # Using POST so large multi-paragraph captions don't exceed URL limits
            response = requests.post(url, params=params, data={"q": text}, headers=headers, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result and isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
                    # Stitch together all translated segments preserving line breaks
                    translated_segments = [item[0] for item in result[0] if item and item[0]]
                    translated = "".join(translated_segments).strip()
                    if translated:
                        print(f"[DEBUG] Successfully translated caption to Persian.")
                        return translated
            else:
                print(f"[DEBUG] Translation HTTP {response.status_code}. Retrying...")
                
        except Exception as e:
            print(f"[DEBUG] Translation attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    print("[DEBUG] Translation failed after max retries. Retaining original text as fallback.")
    return text

def send_to_telegram(media_type, media_url, caption):
    if media_type == "video":
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
        payload = {
            "chat_id": CHANNEL_ID,
            "video": media_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
    elif media_type == "photo":
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHANNEL_ID,
            "photo": media_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHANNEL_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

    try:
        response = requests.post(url, json=payload, timeout=20)
        return response.json()
    except Exception as e:
        print(f"[DEBUG] Network error calling Telegram API: {e}")
        return None

def main():
    last_id = get_last_processed_id()
    print(f"[DEBUG] Current stored last_id: {last_id}")

    posts = scrape_channel()
    if not posts:
        print("[DEBUG] No posts were successfully parsed. Exiting script.")
        return

    posts = sorted(posts, key=lambda x: x["id"])
    print(f"[DEBUG] Scraped post IDs range from {posts[0]['id']} to {posts[-1]['id']}")

    if last_id == 0:
        # First run / Reset state: Pull posts from the last 1 hour
        print("[DEBUG] First run or reset detected. Filtering posts from the last 1 hour...")
        new_posts = []
        now_utc = datetime.now(timezone.utc)

        for post in posts:
            if post["date_str"]:
                try:
                    post_time = datetime.fromisoformat(post["date_str"])
                    time_diff = now_utc - post_time
                    diff_seconds = time_diff.total_seconds()

                    # If published in the last 1 hour (3600 seconds)
                    if 0 <= diff_seconds <= 3600:
                        new_posts.append(post)
                        print(f"[DEBUG] Post {post['id']} was published {int(diff_seconds // 60)} minutes ago. Selected.")
                except Exception as e:
                    print(f"[DEBUG] Error parsing date for post {post['id']}: {e}")

        if not new_posts:
            print("[DEBUG] No posts found in the last 1 hour. Selecting the absolute latest 1 post to test.")
            new_posts = [posts[-1]]
    else:
        new_posts = [p for p in posts if p["id"] > last_id]

    if not new_posts:
        print("[DEBUG] No new posts detected above last_id.")
        return

    print(f"[DEBUG] Found {len(new_posts)} posts to process.")

    for post in new_posts:
        print(f"\n--- Processing Post {post['id']} ---")

        translated_text = translate_to_persian(post["text"])
        escaped_text = html.escape(translated_text) if translated_text else ""

        if escaped_text:
            caption = f"<blockquote>{escaped_text}</blockquote>\n\n"
        else:
            caption = ""

        # Signature and hashtags
        caption += f'<a href="{post["link"]}">Clash Report 🇹🇷</a>\n🫰@secretollah\n#خبر\n#سیاست'

        # Decide media type
        if post["video_url"]:
            media_type = "video"
            media_url = post["video_url"]
            print(f"[DEBUG] Detected Video Post. URL: {media_url}")
        elif post["photo_url"]:
            media_type = "photo"
            media_url = post["photo_url"]
            print(f"[DEBUG] Detected Photo Post. URL: {media_url}")
        else:
            media_type = "text"
            media_url = None
            print("[DEBUG] Detected Text-Only Post.")

        res = send_to_telegram(media_type, media_url, caption)
        print(f"[DEBUG] Telegram Response for {post['id']}: {res}")

        if res and res.get("ok"):
            print(f"[DEBUG] Successfully posted ID {post['id']} to Telegram.")
            last_id = post["id"]
            save_last_processed_id(last_id)
        else:
            # Fallback to text-only if media sending fails
            if media_type != "text":
                print(f"[DEBUG] Media send failed. Retrying post {post['id']} as text-only.")
                fallback_res = send_to_telegram("text", None, caption)
                print(f"[DEBUG] Telegram Fallback Response: {fallback_res}")
                if fallback_res and fallback_res.get("ok"):
                    print(f"[DEBUG] Fallback successfully posted ID {post['id']}.")
                    last_id = post["id"]
                    save_last_processed_id(last_id)
                    continue

            print(f"[ERROR] Failed to post ID {post['id']}.")
            last_id = post["id"]
            save_last_processed_id(last_id)

if __name__ == "__main__":
    main()
