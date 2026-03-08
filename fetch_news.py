#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("=== ЗАПУСК РАБОЧЕЙ ВЕРСИИ ===")

import feedparser
import json
import time
from datetime import datetime
import hashlib
import random
import requests
from urllib.parse import urlparse
import re
import os

print("✅ Базовые библиотеки загружены")

import firebase_admin
from firebase_admin import credentials, firestore
print("✅ Firebase загружен")

# Инициализация Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
print("✅ Firebase инициализирован")

# ============ НАСТРОЙКИ ============
TIMEOUT = 5
MAX_ARTICLES_PER_FEED = 2
REQUEST_DELAY = 1

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': ['https://lenta.ru/rss/news/politics', 'https://ria.ru/export/rss2/politics/index.xml'],
    'Экономика': ['https://lenta.ru/rss/news/economics', 'https://ria.ru/export/rss2/economy/index.xml'],
    'Спорт': ['https://lenta.ru/rss/news/sport', 'https://ria.ru/export/rss2/sport/index.xml']
}

def extract_images_from_entry(entry):
    images = []
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    return list(dict.fromkeys(images))

def fetch_and_save():
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
                    print(f"    ✅ {entry.title[:50]}...")
                    images = extract_images_from_entry(entry)
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
                    time.sleep(REQUEST_DELAY)
            except:
                continue
    
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Добавлено: {new_count}")
    print(f"📊 Всего: {len(all_news)}")

if __name__ == '__main__':
    fetch_and_save()