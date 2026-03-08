#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import json
import hashlib
import re
from datetime import datetime
import requests
import os
import html
import sys
import traceback

print("=" * 60)
print("=== УПРОЩЕННЫЙ СБОР НОВОСТЕЙ (RSS + ИИ) ===")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ============ НАСТРОЙКИ ============
MAX_ARTICLES_PER_FEED = 30
REQUEST_DELAY = 0

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': ['https://tass.ru/rss/v2.xml'],
    'Экономика': ['https://tass.ru/rss/v2.xml'],
    'Технологии': ['https://tass.ru/rss/v2.xml'],
    'Культура': ['https://tass.ru/rss/v2.xml'],
    'Спорт': ['https://tass.ru/rss/v2.xml'],
}

# ============ НАСТРОЙКИ ИИ ============
USE_AI = True
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"
AI_API_KEY = "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"

if not AI_API_KEY or AI_API_KEY == "sk-or-v1-...":
    print("⚠️ ВНИМАНИЕ: API ключ не настроен! ИИ будет отключен")
    USE_AI = False
else:
    print(f"✅ API ключ загружен, ИИ активен")

def clean_text(text):
    """Очистка текста"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def ai_rewrite_text(text, title):
    """Переписывание текста через ИИ"""
    if not text or len(text) < 100 or not USE_AI:
        return text
    
    try:
        print(f"    🤖 ИИ обрабатывает...")
        
        prompt = f"""Перепиши эту новость своими словами. Сохрани все факты.
Напиши связный текст из 3-5 предложений.

Заголовок: {title}
Текст: {text[:1000]}

Переписанный текст:"""
        
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tolk-1.web.app",
        }
        
        data = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"]
            return clean_text(rewritten)
        
        return text
    except:
        return text

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ")
    print(f"{'='*60}")
    
    if not os.path.exists('public'):
        os.makedirs('public')
    
    json_path = 'public/news_data_v3.json'
    
    # Загружаем существующие новости
    existing_links = set()
    old_news = []
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                old_news = json.load(f)
                for item in old_news:
                    if item.get('originalLink'):
                        existing_links.add(item['originalLink'])
            print(f"📊 Загружено {len(old_news)} старых новостей")
        except:
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    # Берем только одну категорию для теста
    feed_url = 'https://tass.ru/rss/v2.xml'
    
    print(f"\n📡 Загрузка RSS...")
    feed = feedparser.parse(feed_url)
    
    if not feed.entries:
        print("❌ Нет записей в RSS")
        return
    
    print(f"📊 Найдено записей: {len(feed.entries)}")
    
    for i, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_FEED]):
        if entry.link in existing_links:
            continue
        
        print(f"\n  🔍 [{i+1}] {entry.title[:60]}...")
        
        # Получаем текст из RSS
        full_text = entry.get('summary', '') or entry.get('description', '')
        full_text = re.sub(r'<[^>]+>', '', full_text)
        full_text = clean_text(full_text)
        
        # Применяем ИИ
        if USE_AI and full_text:
            rewritten_text = ai_rewrite_text(full_text, entry.title)
            if rewritten_text and len(rewritten_text) > 50:
                full_text = rewritten_text
        
        # Ищем картинку
        images = []
        summary = entry.get('summary', '') or entry.get('description', '')
        img_match = re.search(r'<img[^>]+src="([^">]+)"', summary)
        if img_match:
            img_url = img_match.group(1)
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            images.append(img_url)
        
        # Форматируем
        content_html = f'<p>{full_text}</p>'
        
        # Создаем запись
        news_item = {
            'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
            'title': entry.title[:200],
            'description': full_text[:200] + '...',
            'content': content_html,
            'category': 'Новости',
            'images': images,
            'originalLink': entry.link,
            'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
            'timestamp': datetime.now().isoformat()
        }
        
        all_news.append(news_item)
        existing_links.add(entry.link)
        new_count += 1
        
        print(f"    ✅ СОХРАНЕНО | Текст: {len(full_text)} символов")
    
    # Сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if len(all_news) > 200:
        all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"{'='*60}")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()