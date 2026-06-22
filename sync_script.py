import os
import re
import html
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

BOT_TOKEN = "8259373992:AAFZNTWpHQp2Pf_3nb_gmbquxevI2GeYGeg"
CHANNEL_ID = "-1003623628162"
SOURCE_CHANNEL = "clashreport"
STATE_FILE = "last_id.txt"

def get_last_processed_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                content = f.read().strip()
                return int(content) if content else 0
        except Exception:
            return 0
    return 0

def save_last_processed_id(last_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(last_id))

def scrape_channel():
    url = f"https://t.me/s/{SOURCE_CHANNEL}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Error: Could not retrieve web preview.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    messages = soup.find_all("div", class_="tgme_widget_message_wrap")
    
    parsed_posts = []
    for msg in messages:
        msg_body = msg.find("div", class_="tgme_widget_message")
        if not msg_body:
            continue
        
        data_post = msg_body.get("data-post")
        if not data_post:
            continue
            
        try:
            post_id = int(data_post.split("/")[-1])
        except ValueError:
            continue
            
        post_link = f"https://t.me/{data_post}"
        
        # Text extraction
        text_elem = msg_body.find("div", class_="tgme_widget_message_text")
        text = text_elem.get_text() if text_elem else ""
        
        # Video extraction
        video_elem = msg_body.find("video", class_="tgme_widget_message_video")
        video_url = video_elem.get("src") if video_elem else None
        
        # Photo/Screenshot extraction
        photo_elem = msg_body.find("a", class_="tgme_widget_message_photo_wrap")
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
            "video_url": video_url,
            "photo_url": photo_url
        })
        
    return parsed_posts

def translate_to_persian(text):
    if not text:
        return ""
    try:
        # Translates Turkish/English to Persian
        translated = GoogleTranslator(source='auto', target='fa').translate(text)
        return translated
    except Exception as e:
        print(f"Translation error: {e}")
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
        print(f"Failed to send message: {e}")
        return None

def main():
    last_id = get_last_processed_id()
    print(f"Last processed ID: {last_id}")
    
    posts = scrape_channel()
    if not posts:
        print("No posts found.")
        return
        
    posts = sorted(posts, key=lambda x: x["id"])
    
    # Initialize state file on the first run to prevent spamming old posts
    if last_id == 0:
        latest_id = posts[-1]["id"]
        save_last_processed_id(latest_id)
        print(f"Initialized last_id.txt with the latest ID: {latest_id}. Future posts will be processed.")
        return

    new_posts = [p for p in posts if p["id"] > last_id]
    
    if not new_posts:
        print("No new posts.")
        return
        
    print(f"Processing {len(new_posts)} new posts...")
    
    for post in new_posts:
        print(f"Processing ID: {post['id']}")
        
        translated_text = translate_to_persian(post["text"])
        escaped_text = html.escape(translated_text) if translated_text else ""
        
        # Telegram blockquote wrapper for quotation style styling
        if escaped_text:
            caption = f"<blockquote>{escaped_text}</blockquote>\n\n"
        else:
            caption = ""
            
        caption += f'<a href="{post["link"]}">Clash Report 🇹🇷</a>\n🫰secretollah'
        
        if post["video_url"]:
            media_type = "video"
            media_url = post["video_url"]
        elif post["photo_url"]:
            media_type = "photo"
            media_url = post["photo_url"]
        else:
            media_type = "text"
            media_url = None
            
        res = send_to_telegram(media_type, media_url, caption)
        if res and res.get("ok"):
            print(f"Successfully sent ID {post['id']}")
            last_id = post["id"]
            save_last_processed_id(last_id)
        else:
            print(f"Failed to send ID {post['id']}: {res}")
            # Move queue forward even if posting fails to prevent getting stuck
            last_id = post["id"]
            save_last_processed_id(last_id)

if __name__ == "__main__":
    main()
