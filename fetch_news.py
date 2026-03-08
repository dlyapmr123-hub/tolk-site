#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import json
import time
import hashlib
import re
from datetime import datetime
import requests
import os

print("=== ЗАПУСК СКРИПТА ===")

# ============ НАСТРОЙКИ ============
TIMEOUT = 5
MAX_ARTICLES_PER_FEED = 3
REQUEST_DELAY = 1

# ============ RSS ИСТОЧНИКИ (ВСЕ КАТЕГОРИИ) ============
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
    """Извлечение картинок из RSS"""
    images = []
    
    # Из media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    
    # Из summary (ищем теги img)
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        import re
        img_urls = re.findall(r'<img[^>]+src="([^">]+)"', summary)
        for url in img_urls:
            if url.startswith('//'):
                url = 'https:' + url
            images.append(url)
    
    # Убираем дубликаты
    seen = set()
    unique = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    
    return unique[:3]  # Максимум 3 картинки

def fetch_article_text(url):
    """Загружает текст статьи (упрощенно)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        
        # Просто ищем текст в HTML
        import re
        text = response.text
        # Удаляем скрипты и стили
        text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
        # Удаляем все теги
        text = re.sub(r'<[^>]+>', ' ', text)
        # Чистим пробелы
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text[:1000]  # Первые 1000 символов
        
    except:
        return None

def ai_rewrite_text(text):
    """Простое перефразирование (без API)"""
    if not text or len(text) < 100:
        return text
    
    # Простая замена слов
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил'],
        'произошло': ['случилось', 'состоялось', 'имело место'],
        'новый': ['свежий', 'актуальный', 'последний'],
        'важный': ['значительный', 'ключевой', 'главный'],
        'россия': ['РФ', 'Российская Федерация', 'наша страна']
    }
    
    for word, replacements in synonyms.items():
        if word in text:
            import random
            text = text.replace(word, random.choice(replacements))
    
    return text

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    json_path = 'public/news_data_v3.json'
    
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
            print(f"Загружено {len(old_news)} старых новостей")
        except:
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category}")
        
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  + {entry.title[:70]}...")
                    
                    # Получаем картинки
                    images = extract_images_from_entry(entry)
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    if description:
                        import re
                        description = re.sub(r'<[^>]+>', '', description)
                        description = description[:200]
                    
                    # Пробуем загрузить текст
                    full_text = fetch_article_text(entry.link)
                    
                    if full_text:
                        rewritten = ai_rewrite_text(full_text)
                        # Разбиваем на абзацы
                        paragraphs = rewritten.split('. ')
                        content_html = ''
                        for i, p in enumerate(paragraphs[:5]):
                            if p.strip():
                                content_html += f'<p>{p.strip()}.</p>\n'
                    else:
                        content_html = f'<p>{description}</p>'
                    
                    # Создаём запись
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
                print(f"  Ошибка: {feed_url}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего: {len(all_news)}")
    print(f"   Новых: {new_count}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}")

if __name__ == '__main__':
    fetch_and_save()