#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import time
import hashlib
import random
import re
from datetime import datetime
import feedparser
import requests
from urllib.parse import urlparse

print("=== ЗАПУСК СКРИПТА ===")

# ============ ФУНКЦИЯ ПЕРЕФРАЗИРОВАНИЯ ============
def ai_rewrite_text(text):
    if not text or len(text) < 50:
        return text
    
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил'],
        'произошло': ['случилось', 'состоялось', 'имело место'],
        'новый': ['свежий', 'актуальный', 'последний'],
        'важный': ['значительный', 'ключевой', 'главный']
    }
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = []
    
    for sentence in sentences:
        words = sentence.split()
        new_words = []
        
        for word in words:
            word_lower = word.lower().strip('.,!?()"«»')
            if word_lower in synonyms and random.random() > 0.5:
                replacement = random.choice(synonyms[word_lower])
                if word[0].isupper():
                    replacement = replacement.capitalize()
                new_words.append(replacement)
            else:
                new_words.append(word)
        
        new_sentence = ' '.join(new_words)
        
        if random.random() > 0.7 and len(result) < len(sentences) - 1:
            intros = ['По информации источников, ', 'Как стало известно, ']
            new_sentence = random.choice(intros) + new_sentence[0].lower() + new_sentence[1:]
        
        result.append(new_sentence)
    
    return ' '.join(result)

# ============ ЗАГРУЗКА СТАТЬИ ============
def fetch_full_article(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        
        text = soup.get_text()
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()[:2000]
        
    except:
        return None

# ============ FIREBASE ============
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    print("✅ Firebase загружен")
    
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase инициализирован")
    else:
        db = None
except Exception as e:
    print(f"⚠️ Ошибка Firebase: {e}")
    db = None

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
    print("\n=== НАЧАЛО СБОРА НОВОСТЕЙ ===")
    
    json_path = 'public/news_data_v2.json'
    
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
        print(f"\n📡 {category}")
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:3]:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  ✅ {entry.title[:50]}...")
                    
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
                        'description': description[:150] + '...',
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
                    
                    if db:
                        try:
                            db.collection('news').add(news_item)
                        except:
                            pass
                    
                    time.sleep(1)
                    
            except Exception as e:
                print(f"  ⚠️ Ошибка: {feed_url}")
                continue
    
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего: {len(all_news)}")
    print(f"   Новых: {new_count}")
    print(f"{'='*50}")

if __name__ == '__main__':
    fetch_and_save()