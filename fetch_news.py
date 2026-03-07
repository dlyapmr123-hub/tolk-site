# fetch_news.py - ПОЛНАЯ ВЕРСИЯ
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
TIMEOUT = 5
MAX_ARTICLES_PER_FEED = 3
REQUEST_DELAY = 1

# Инициализация Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': [
        'https://lenta.ru/rss/news/politics',
        'https://ria.ru/export/rss2/politics/index.xml',
        'https://tass.ru/rss/v2.xml'
    ],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://www.rbc.ru/rss/'
    ],
    'Технологии': [
        'https://lenta.ru/rss/news/technology',
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://habr.com/ru/rss/news/?fl=ru'
    ],
    'Авто': [
        'https://lenta.ru/rss/news/auto',
        'https://motor.ru/rss',
        'https://www.autonews.ru/export/rss2/news/index.xml'
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
        'https://stopgame.ru/rss/news.xml'
    ],
    'Культура': [
        'https://lenta.ru/rss/news/art',
        'https://ria.ru/export/rss2/culture/index.xml',
        'https://www.mk.ru/rss/culture/index.xml'
    ],
    'Спорт': [
        'https://lenta.ru/rss/news/sport',
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://www.championat.com/news/rss/'
    ]
}

def extract_images_from_entry(entry):
    """Извлечение картинок"""
    images = []
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    return list(dict.fromkeys(images))

def fetch_full_article(url):
    """Загрузка текста статьи"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style']):
            tag.decompose()
        text = soup.get_text()
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text[:1500]
    except:
        return None

def ai_rewrite_text(text):
    """Перефразирование"""
    if not text:
        return text
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил'],
        'произошло': ['случилось', 'состоялось', 'имело место'],
        'новый': ['свежий', 'актуальный', 'последний'],
        'важный': ['значительный', 'ключевой', 'главный']
    }
    for word, replacements in synonyms.items():
        if word in text and random.random() > 0.5:
            text = text.replace(word, random.choice(replacements))
    return text

def fetch_and_save():
    """Основная функция"""
    print(f"\n{'='*60}")
    print(f"  🔴 НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    json_path = 'public/news_data.json'
    
    existing_links = set()
    old_news = []
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            old_news = json.load(f)
            for item in old_news:
                if item.get('originalLink'):
                    existing_links.add(item['originalLink'])
        print(f"📚 Загружено {len(old_news)} новостей")
    
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
                    
                    print(f"    ✅ {entry.title[:60]}...")
                    
                    images = extract_images_from_entry(entry)
                    description = entry.get('summary', '')[:200]
                    full_text = fetch_full_article(entry.link)
                    
                    if full_text:
                        content = ai_rewrite_text(full_text)
                        content_html = f'<p>{content[:500]}</p>'
                    else:
                        content_html = f'<p>{description}</p>'
                    
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:150] + '...' if len(description) > 150 else description,
                        'content': content_html,
                        'category': category,
                        'images': images[:3],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                continue
    
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ:")
    print(f"   📊 Всего: {len(all_news)}")
    print(f"   🆕 Добавлено: {new_count}")
    print(f"{'='*60}")

if __name__ == '__main__':
    fetch_and_save()