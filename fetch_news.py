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
import time

print("=" * 60)
print("=== СБОР НОВОСТЕЙ (ПОЛНЫЙ ТЕКСТ) ===")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ============ НАСТРОЙКИ ============
MAX_ARTICLES_PER_FEED = 20

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': ['https://ria.ru/export/rss2/politics/index.xml'],
    'Экономика': ['https://ria.ru/export/rss2/economy/index.xml'],
    'Технологии': ['https://ria.ru/export/rss2/technology/index.xml'],
    'Культура': ['https://ria.ru/export/rss2/culture/index.xml'],
    'Спорт': ['https://ria.ru/export/rss2/sport/index.xml'],
}

# ============ НАСТРОЙКИ ИИ ============
USE_AI = True
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"
AI_API_KEY = "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"

def clean_html(text):
    """Удаление HTML тегов"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_full_text(entry):
    """Извлечение ПОЛНОГО текста из RSS"""
    
    # Пробуем разные поля где может быть текст
    
    # 1. content (самое полное)
    if hasattr(entry, 'content'):
        for content in entry.content:
            if content.get('value'):
                text = clean_html(content['value'])
                if len(text) > 200:
                    print(f"      📝 Текст из content: {len(text)} символов")
                    return text
    
    # 2. content_encoded
    if hasattr(entry, 'content_encoded'):
        text = clean_html(entry.content_encoded)
        if len(text) > 200:
            print(f"      📝 Текст из content_encoded: {len(text)} символов")
            return text
    
    # 3. summary_detail
    if hasattr(entry, 'summary_detail') and hasattr(entry.summary_detail, 'value'):
        text = clean_html(entry.summary_detail.value)
        if len(text) > 200:
            print(f"      📝 Текст из summary_detail: {len(text)} символов")
            return text
    
    # 4. description
    if hasattr(entry, 'description'):
        text = clean_html(entry.description)
        if len(text) > 200:
            print(f"      📝 Текст из description: {len(text)} символов")
            return text
    
    # 5. summary
    if hasattr(entry, 'summary'):
        text = clean_html(entry.summary)
        if len(text) > 200:
            print(f"      📝 Текст из summary: {len(text)} символов")
            return text
    
    return None

def ai_rewrite(text, title):
    """ИИ переписывание"""
    if not text or len(text) < 200 or not USE_AI:
        return text
    
    try:
        prompt = f"""Перепиши эту новость полностью, сохранив все факты.
Напиши связный текст из 4-6 предложений.

Заголовок: {title}
Текст: {text[:1500]}

Переписанный текст:"""
        
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        }
        
        data = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 800
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"]
            rewritten = clean_html(rewritten)
            if len(rewritten) > 100:
                return rewritten
        return text
    except:
        return text

def get_images(entry):
    """Извлечение картинок"""
    images = []
    
    # Из media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                url = media['url']
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
    
    # Из summary (поиск img)
    if hasattr(entry, 'summary'):
        img_matches = re.findall(r'<img[^>]+src="([^">]+)"', entry.summary)
        for url in img_matches:
            if url.startswith('//'):
                url = 'https:' + url
            images.append(url)
    
    return list(set(images))[:3]

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ")
    print(f"{'='*60}")
    
    if not os.path.exists('public'):
        os.makedirs('public')
    
    json_path = 'public/news_data_v3.json'
    
    # Загружаем существующие
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
                print(f"  📰 Загрузка RSS...")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    continue
                
                print(f"  📊 Найдено записей: {len(feed.entries)}")
                
                for i, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_FEED]):
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 [{i+1}] {entry.title[:60]}...")
                    
                    # ПОЛУЧАЕМ ПОЛНЫЙ ТЕКСТ
                    full_text = get_full_text(entry)
                    
                    if not full_text:
                        print(f"    ❌ Нет текста")
                        continue
                    
                    print(f"    ✅ Найден текст: {len(full_text)} символов")
                    
                    # ПРИМЕНЯЕМ ИИ
                    if USE_AI:
                        rewritten = ai_rewrite(full_text, entry.title)
                        if rewritten and len(rewritten) > 100:
                            full_text = rewritten
                            print(f"    🤖 После ИИ: {len(full_text)} символов")
                    
                    # КАРТИНКИ
                    images = get_images(entry)
                    
                    # ФОРМАТИРУЕМ В HTML
                    # Разбиваем на предложения для красивого вывода
                    sentences = re.split(r'(?<=[.!?])\s+', full_text)
                    content_html = ''
                    for sent in sentences[:8]:  # Максимум 8 предложений
                        if sent.strip():
                            content_html += f'<p>{sent.strip()}</p>\n'
                    
                    # ОПИСАНИЕ
                    description = full_text[:200] + '...' if len(full_text) > 200 else full_text
                    
                    # СОЗДАЕМ ЗАПИСЬ
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                        'title': entry.title[:200],
                        'description': description,
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
                    
                    print(f"    ✅ СОХРАНЕНО | Текст: {len(full_text)} символов | Картинок: {len(images)}")
                    
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue
    
    # СОРТИРУЕМ
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if len(all_news) > 300:
        all_news = all_news[:300]
    
    # СОХРАНЯЕМ
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()