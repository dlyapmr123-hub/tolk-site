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
from urllib.parse import urljoin, urlparse
import html
import sys
import traceback

# Принудительно включаем вывод
try:
    sys.stdout.reconfigure(line_buffering=True)
except:
    pass

print("=" * 60)
print("=== ЗАПУСК СКРИПТА СБОРА НОВОСТЕЙ ===")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# Пытаемся импортировать BeautifulSoup
try:
    from bs4 import BeautifulSoup
    print("✅ BeautifulSoup импортирован успешно")
except ImportError:
    print("❌ BeautifulSoup не найден, устанавливаем...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "lxml"])
    from bs4 import BeautifulSoup
    print("✅ BeautifulSoup установлен и импортирован")

# ============ НАСТРОЙКИ ============
TIMEOUT = 10  # Уменьшаем таймаут
MAX_ARTICLES_PER_FEED = 3  # Уменьшаем количество статей
REQUEST_DELAY = 2
MAX_IMAGES = 3

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': [
        'https://lenta.ru/rss/news/politics',
        'https://ria.ru/export/rss2/politics/index.xml',
    ],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
    ],
    'Технологии': [
        'https://lenta.ru/rss/news/technology',
        'https://ria.ru/export/rss2/technology/index.xml',
    ],
    'Авто': [
        'https://lenta.ru/rss/news/auto',
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
    ],
    'Культура': [
        'https://lenta.ru/rss/news/art',
    ],
    'Спорт': [
        'https://lenta.ru/rss/news/sport',
        'https://ria.ru/export/rss2/sport/index.xml',
    ]
}

# ============ НАСТРОЙКИ ИИ ============
USE_AI = True
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"
AI_API_KEY = "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"

print(f"📊 Настройки: TIMEOUT={TIMEOUT}, MAX_ARTICLES={MAX_ARTICLES_PER_FEED}")
print(f"🤖 ИИ: {'ВКЛЮЧЕН' if USE_AI else 'ВЫКЛЮЧЕН'}")
print("=" * 60)

def clean_text(text):
    """Быстрая очистка текста"""
    if not text:
        return ""
    
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    
    # Короткий список мусора
    garbage = ['реклама', 'подпишись', 'telegram', 'vk', 'вконтакте', 
               'youtube', 'instagram', 'cookie', 'читать далее', 'фото:', 'видео:']
    
    for word in garbage:
        text = re.sub(word, '', text, flags=re.IGNORECASE)
    
    return text.strip()

def extract_text_fast(html_content):
    """Быстрое извлечение текста без сложного парсинга"""
    if not html_content:
        return None, []
    
    images = []
    
    try:
        # Быстро ищем картинки
        img_matches = re.findall(r'<img[^>]+src="([^">]+)"', html_content)
        for url in img_matches[:MAX_IMAGES]:
            if url.startswith('//'):
                url = 'https:' + url
            if re.search(r'\.(jpg|jpeg|png|webp)(\?|$)', url.lower()):
                if 'logo' not in url.lower() and 'icon' not in url.lower():
                    images.append(url)
        
        # Ищем текст в параграфах
        p_matches = re.findall(r'<p[^>]*>(.*?)</p>', html_content, re.DOTALL)
        text_parts = []
        
        for p in p_matches[:10]:
            # Удаляем теги внутри параграфа
            p_text = re.sub(r'<[^>]+>', ' ', p)
            p_text = html.unescape(p_text)
            p_text = re.sub(r'\s+', ' ', p_text).strip()
            
            if len(p_text) > 50 and 'реклама' not in p_text.lower():
                text_parts.append(p_text)
        
        if text_parts:
            return ' '.join(text_parts), images
        
        return None, images
        
    except Exception as e:
        return None, images

def fetch_article_data(url):
    """Быстрая загрузка статьи"""
    try:
        print(f"    📥 Загрузка: {url[:50]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Устанавливаем маленький таймаут
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code != 200:
            return None, []
        
        text, images = extract_text_fast(response.text)
        
        if text and len(text) > 100:
            print(f"    ✅ {len(text)} символов, {len(images)} картинок")
            return text, images
        
        return None, images
        
    except requests.exceptions.Timeout:
        print(f"    ⏱️ Таймаут")
        return None, []
    except Exception as e:
        print(f"    ⚠️ Ошибка")
        return None, []

def ai_rewrite_text(text, title, category):
    """Быстрое перефразирование"""
    if not text or len(text) < 200 or not USE_AI:
        return text
    
    try:
        # Берем только начало текста для ускорения
        short_text = text[:1000]
        
        prompt = f"""Перепиши кратко: {title}
        
Оригинал: {short_text}

Краткий пересказ (3-4 предложения):"""
        
        headers = {"Authorization": f"Bearer {AI_API_KEY}"}
        data = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 300
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
    
    # Создаем папку public
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
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category}")
        
        for feed_url in feeds:
            try:
                print(f"  📰 RSS: {feed_url.split('/')[-1]}")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 {entry.title[:60]}...")
                    
                    # Загружаем текст и картинки
                    full_text, images = fetch_article_data(entry.link)
                    
                    if not full_text:
                        # Если текст не загрузился, используем описание из RSS
                        full_text = entry.get('summary', '') or entry.get('description', '')
                        full_text = re.sub(r'<[^>]+>', '', full_text)
                        full_text = clean_text(full_text)
                    
                    # Применяем ИИ
                    if USE_AI and full_text:
                        full_text = ai_rewrite_text(full_text, entry.title, category)
                    
                    # Форматируем
                    content_html = f'<p>{full_text}</p>'
                    
                    # Создаем запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                        'title': entry.title[:150],
                        'description': full_text[:150] + '...' if len(full_text) > 150 else full_text,
                        'content': content_html,
                        'category': category,
                        'images': images,
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
                    time.sleep(1)  # Маленькая задержка
                    
            except Exception as e:
                print(f"  ⚠️ Ошибка RSS")
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