# fetch_news.py (СУПЕР-БЫСТРАЯ ВЕРСИЯ)
import feedparser
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import hashlib
import requests
import os
import firebase_admin
from firebase_admin import credentials, firestore

# Инициализация Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# RSS ИСТОЧНИКИ (только основные)
RSS_FEEDS = {
    'Политика': ['https://lenta.ru/rss/news/politics', 'https://ria.ru/export/rss2/politics/index.xml'],
    'Экономика': ['https://lenta.ru/rss/news/economics', 'https://ria.ru/export/rss2/economy/index.xml'],
    'Спорт': ['https://lenta.ru/rss/news/sport', 'https://ria.ru/export/rss2/sport/index.xml']
}

def fetch_and_save():
    print(f"\n[{datetime.now()}] НАЧАЛО СБОРА")
    
    json_path = 'public/news_data.json'
    
    existing_links = set()
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            old_news = json.load(f)
            for item in old_news:
                if item.get('originalLink'):
                    existing_links.add(item['originalLink'])
            print(f"Загружено {len(old_news)} старых новостей")
    else:
        old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\nКатегория: {category}")
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:3]:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  + {entry.title[:50]}...")
                    
                    images = []
                    if hasattr(entry, 'media_content'):
                        for media in entry.media_content:
                            if media.get('url'):
                                images.append(media['url'])
                    
                    description = entry.get('summary', '')[:200]
                    
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description,
                        'content': f'<p>{description}</p>',
                        'category': category,
                        'images': images[:2],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
            except Exception as e:
                print(f"  Ошибка: {feed_url}")
                continue
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news[:200], f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Добавлено новых: {new_count}")
    print(f"📊 Всего: {len(all_news[:200])}")

if __name__ == '__main__':
    fetch_and_save()