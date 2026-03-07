# fetch_news.py (БЫСТРАЯ ВЕРСИЯ)
import feedparser
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import hashlib
import random
import requests
from urllib.parse import urlparse
import re
import os
import firebase_admin
from firebase_admin import credentials, firestore

# ============ НАСТРОЙКИ ============
TIMEOUT = 3  # Таймаут 3 секунды
MAX_ARTICLES_PER_FEED = 2  # Только 2 статьи с ленты
MAX_PARAGRAPHS = 4  # Только 4 абзаца

# Инициализация Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': ['https://lenta.ru/rss/news/politics', 'https://ria.ru/export/rss2/politics/index.xml'],
    'Экономика': ['https://lenta.ru/rss/news/economics', 'https://ria.ru/export/rss2/economy/index.xml'],
    'Технологии': ['https://lenta.ru/rss/news/technology', 'https://ria.ru/export/rss2/technology/index.xml'],
    'Авто': ['https://lenta.ru/rss/news/auto', 'https://motor.ru/rss'],
    'Киберспорт': ['https://www.cybersport.ru/rss', 'https://stopgame.ru/rss/news.xml'],
    'Культура': ['https://lenta.ru/rss/news/art', 'https://ria.ru/export/rss2/culture/index.xml'],
    'Спорт': ['https://lenta.ru/rss/news/sport', 'https://ria.ru/export/rss2/sport/index.xml']
}

def extract_images_from_entry(entry):
    """Быстрое извлечение картинок"""
    images = []
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    return list(dict.fromkeys(images))

def fetch_full_article(url):
    """Быстрая загрузка статьи с таймаутом"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            return None, []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup.find_all(['script', 'style']):
            element.decompose()
        
        text = soup.get_text()
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text[:1000], []  # Только первые 1000 символов
        
    except:
        return None, []

def ai_rewrite_text(text):
    if not text or len(text) < 50:
        return text
    
    synonyms = {'сказал': 'заявил', 'сообщил': 'проинформировал'}
    for old, new in synonyms.items():
        text = text.replace(old, new)
    return text

def fetch_and_save():
    print(f"\n[{datetime.now()}] 🔴 НАЧАЛО СБОРА")
    
    json_path = 'public/news_data.json'
    
    existing_links = set()
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            old_news = json.load(f)
            for item in old_news:
                if item.get('originalLink'):
                    existing_links.add(item['originalLink'])
            print(f"📚 Загружено {len(old_news)} старых новостей")
    else:
        old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category}")
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"    ✅ {entry.title[:40]}...")
                    
                    images = extract_images_from_entry(entry)
                    full_text, _ = fetch_full_article(entry.link)
                    
                    description = entry.get('summary', '')[:100]
                    
                    if full_text:
                        content = ai_rewrite_text(full_text)
                        content_html = f'<p>{content[:500]}</p>'
                    else:
                        content_html = f'<p>{description}</p>'
                    
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:150],
                        'description': description,
                        'content': content_html,
                        'category': category,
                        'images': images[:2],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    time.sleep(1)
                    
            except Exception as e:
                print(f"    ❌ Ошибка: {feed_url}")
                continue
    
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Добавлено новых: {new_count}")
    print(f"📊 Всего: {len(all_news)}")

if __name__ == '__main__':
    fetch_and_save()