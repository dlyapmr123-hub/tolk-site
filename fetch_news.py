#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import time
import hashlib
from datetime import datetime
import feedparser
import requests
from urllib.parse import urlparse
import re

print("=== ЗАПУСК СКРИПТА ===")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print("=" * 50)

# Firebase импорт с защитой
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    print("✅ Firebase загружен")
    FIREBASE_OK = True
except Exception as e:
    print(f"⚠️ Ошибка загрузки Firebase: {e}")
    FIREBASE_OK = False

# Инициализация Firebase если есть ключ
if FIREBASE_OK and os.path.exists("serviceAccountKey.json"):
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase инициализирован")
    except Exception as e:
        print(f"⚠️ Ошибка инициализации Firebase: {e}")
        db = None
else:
    db = None
    print("⚠️ Firebase не используется")

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

def fetch_and_save():
    print("\n=== НАЧАЛО СБОРА НОВОСТЕЙ ===")
    
    json_path = 'public/news_data.json'
    
    # Загружаем существующие ссылки
    existing_links = set()
    old_news = []
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                old_news = json.load(f)
                for item in old_news:
                    if item.get('originalLink'):
                        existing_links.add(item['originalLink'])
            print(f"✅ Загружено {len(old_news)} старых новостей")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки JSON: {e}")
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                entries = feed.entries[:MAX_ARTICLES_PER_FEED]
                
                for entry in entries:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  ✅ {entry.title[:50]}...")
                    
                    # Картинки
                    images = []
                    if hasattr(entry, 'media_content'):
                        for media in entry.media_content:
                            if media.get('url'):
                                images.append(media['url'])
                    
                    # Описание
                    description = entry.get('summary', '')[:200]
                    
                    # Создаём запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description,
                        'content': f'<p>{description}</p>',
                        'category': category,
                        'images': images[:3],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
                    # Сохраняем в Firebase
                    if db:
                        try:
                            db.collection('news').add(news_item)
                        except:
                            pass
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"  ⚠️ Ошибка: {feed_url}")
                continue
    
    # Сохраняем JSON
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Добавлено новых: {new_count}")
    print(f"{'='*50}")

if __name__ == '__main__':
    fetch_and_save()