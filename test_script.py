import os
import re
import html
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

BOT_TOKEN = "8259373992:AAFZNTWpHQp2Pf_3nb_gmbquxevI2GeYGeg"
CHANNEL_ID = "-1003623628162"
SOURCE_CHANNEL = "clashreport"

def scrape_channel():
    url = f"https://t.me/s/{SOURCE_CHANNEL}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    print(f"[DEBUG] Fetching URL: {url}")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("[DEBUG] Failed to load the page.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    messages = soup.select(".tgme_widget_message")
    print(f"[DEBUG] Found {len(messages)} total posts on the page.")
    
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
        
        # Text extraction
        text_elem = msg_body.select_one(".tgme_widget_message_text")
        text = text_elem.get_text() if text_elem else ""
        
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

def translate_to_persian(text):
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source='auto', target='fa').translate(text)
        return translated
    except Exception as e:
        print(f"[DEBUG] Translation warning: {e}")
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
    posts = scrape_channel()
    if not posts:
        print("[DEBUG] No posts were found.")
        return
        
    posts = sorted(posts, key=lambda x: x["id"])
    
    test_posts = []
    now_utc = datetime.now(timezone.utc)
    
    print("\n--- Filtering posts from the last 2 hours ---")
    for post in posts:
        if post["date_str"]:
            try:
                post_time = datetime.fromisoformat(post["date_str"])
                time_diff = now_utc - post_time
                diff_seconds = time_diff.total_seconds()
                
                # Check if post was published within 2 hours (7200 seconds)
                if diff_seconds >= 0 and diff_seconds <= 7200:
                    test_posts.append(post)
                    print(f"Post {post['id']}: Published {int(diff_seconds // 60)} minutes ago.")
            except Exception as e:
                print(f"Could not parse date for post {post['id']}: {e}")
                
    if not test_posts:
        print("[DEBUG] No posts found in the last 2 hours. Selecting the absolute last 2 posts on the page instead.")
        test_posts = posts[-2:]
        
    print(f"\nProcessing {len(test_posts)} posts for the test run...")
    
    for post in test_posts:
        print(f"\n--- Testing Post {post['id']} ---")
        
        translated_text = translate_to_persian(post["text"])
        escaped_text = html.escape(translated_text) if translated_text else ""
        
        if escaped_text:
            caption = f"<blockquote>{escaped_text}</blockquote>\n\n"
        else:
            caption = ""
            
        caption += f'<a href="{post["link"]}">Clash Report 🇹🇷</a>\n🫰secretollah'
        
        if post["video_url"]:
            media_type = "video"
            media_url = post["video_url"]
            print(f"[DEBUG] Sending Video Post. URL: {media_url}")
        elif post["photo_url"]:
            media_type = "photo"
            media_url = post["photo_url"]
            print(f"[DEBUG] Sending Photo/Screenshot Post. URL: {media_url}")
        else:
            media_type = "text"
            media_url = None
            print("[DEBUG] Sending Text-Only Post.")
            
        res = send_to_telegram(media_type, media_url, caption)
        print(f"[DEBUG] Telegram response: {res}")

if __name__ == "__main__":
    main()
