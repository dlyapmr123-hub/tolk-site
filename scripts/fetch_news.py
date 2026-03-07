# scripts/fetch_news.py
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
from google.cloud.firestore import SERVER_TIMESTAMP

# Инициализация Firebase
cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'serviceAccountKey.json')
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

# RSS ИСТОЧНИКИ
RSS_FEEDS = {
    'Политика': ['https://lenta.ru/rss/news/politics', 'https://ria.ru/export/rss2/politics/index.xml'],
    'Экономика': ['https://lenta.ru/rss/news/economics', 'https://ria.ru/export/rss2/economy/index.xml'],
    'Технологии': ['https://lenta.ru/rss/news/technology', 'https://ria.ru/export/rss2/technology/index.xml'],
    'Авто': ['https://lenta.ru/rss/news/auto', 'https://motor.ru/rss'],
    'Киберспорт': ['https://www.cybersport.ru/rss', 'https://stopgame.ru/rss/news.xml'],
    'Культура': ['https://lenta.ru/rss/news/art', 'https://ria.ru/export/rss2/culture/index.xml'],
    'Спорт': ['https://lenta.ru/rss/news/sport', 'https://ria.ru/export/rss2/sport/index.xml']
}

def extract_images(entry):
    """Извлекает картинки из RSS"""
    images = []
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    return list(dict.fromkeys(images))

def fetch_full_article(url):
    """Загружает текст статьи"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav']):
            tag.decompose()
        text = soup.get_text()
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text[:5000]  # Ограничиваем длину
    except:
        return None

def ai_rewrite(text):
    """Простое перефразирование"""
    synonyms = {'сказал': 'заявил', 'сообщил': 'проинформировал'}
    for old, new in synonyms.items():
        text = text.replace(old, new)
    return text

def fetch_and_save():
    """Основная функция"""
    print(f"[{datetime.now()}] 🔄 Начинаем сбор...")
    
    # Получаем существующие ссылки
    existing = set()
    docs = db.collection('news').get()
    for doc in docs:
        if doc.to_dict().get('originalLink'):
            existing.add(doc.to_dict()['originalLink'])
    
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        for url in feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    if entry.link in existing:
                        continue
                    
                    print(f"  ✅ Новая: {entry.title[:50]}...")
                    
                    # Получаем данные
                    images = extract_images(entry)
                    if not images:
                        images = [f'https://loremflickr.com/600/400/{category.lower()}']
                    
                    full_text = fetch_full_article(entry.link)
                    if full_text:
                        content = ai_rewrite(full_text)
                        paragraphs = content.split('\n\n')
                        content_html = ''.join([f'<p>{p}</p>' for p in paragraphs[:8]])
                    else:
                        content_html = f'<p>{entry.get("summary", "Нет текста")}</p>'
                    
                    # Сохраняем в Firebase
                    news_data = {
                        'title': entry.title[:200],
                        'content': content_html,
                        'category': category,
                        'images': images[:3],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': SERVER_TIMESTAMP
                    }
                    
                    db.collection('news').add(news_data)
                    new_count += 1
                    time.sleep(2)
                    
            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
    
    print(f"✅ Добавлено: {new_count} новостей")

if __name__ == '__main__':
    fetch_and_save()