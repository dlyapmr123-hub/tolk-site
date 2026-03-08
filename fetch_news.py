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
print("=== СБОР НОВОСТЕЙ (ТОЛЬКО ПРОВЕРЕННЫЕ ИСТОЧНИКИ) ===")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ============ НАСТРОЙКИ ============
MAX_ARTICLES_PER_FEED = 30

# ============ ТОЛЬКО РАБОЧИЕ ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': [
        'https://ria.ru/export/rss2/politics/index.xml',  # РИА - есть полный текст!
    ],
    'Экономика': [
        'https://ria.ru/export/rss2/economy/index.xml',   # РИА
    ],
    'Технологии': [
        'https://ria.ru/export/rss2/technology/index.xml', # РИА
    ],
    'Культура': [
        'https://ria.ru/export/rss2/culture/index.xml',    # РИА
    ],
    'Спорт': [
        'https://ria.ru/export/rss2/sport/index.xml',      # РИА
    ],
}

# ============ НАСТРОЙКИ ИИ ============
USE_AI = True
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"
AI_API_KEY = "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"

print(f"✅ API ключ загружен, ИИ активен")

def clean_text(text):
    """Очистка текста"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'Читайте также:.*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Фото:.*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Видео:.*$', '', text, flags=re.IGNORECASE)
    return text.strip()

def get_text_from_entry(entry):
    """Извлекаем текст из записи RSS"""
    
    # У РИА текст лежит в summary (там полная статья!)
    if hasattr(entry, 'summary'):
        text = entry.summary
        # Убираем HTML теги
        text = re.sub(r'<[^>]+>', ' ', text)
        text = clean_text(text)
        if len(text) > 100:
            return text
    
    # Если нет summary, пробуем description
    if hasattr(entry, 'description'):
        text = entry.description
        text = re.sub(r'<[^>]+>', ' ', text)
        text = clean_text(text)
        if len(text) > 100:
            return text
    
    return None

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
    except Exception as e:
        return text

def get_image_from_entry(entry):
    """Ищем картинку в записи"""
    images = []
    
    # Ищем в summary
    if hasattr(entry, 'summary'):
        img_match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
        if img_match:
            img_url = img_match.group(1)
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            images.append(img_url)
    
    # Ищем в media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                url = media['url']
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
    
    return images[:3]

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
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category}")
        
        for feed_url in feeds:
            try:
                print(f"  📰 RSS: {feed_url}")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Нет записей")
                    continue
                
                print(f"  📊 Найдено записей: {len(feed.entries)}")
                
                for i, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_FEED]):
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 [{i+1}] {entry.title[:60]}...")
                    
                    # Получаем ТЕКСТ из RSS (у РИА он полный!)
                    full_text = get_text_from_entry(entry)
                    
                    if not full_text:
                        print(f"    ⚠️ Нет текста в RSS")
                        continue
                    
                    print(f"    📝 Текст: {len(full_text)} символов")
                    
                    # Применяем ИИ
                    if USE_AI and full_text:
                        rewritten = ai_rewrite_text(full_text, entry.title)
                        if rewritten and len(rewritten) > 50:
                            full_text = rewritten
                            print(f"    🤖 После ИИ: {len(full_text)} символов")
                    
                    # Получаем картинки
                    images = get_image_from_entry(entry)
                    
                    # Форматируем текст в параграфы
                    sentences = full_text.split('. ')
                    content_html = ''
                    for sent in sentences[:8]:
                        if sent.strip():
                            content_html += f'<p>{sent.strip()}.</p>\n'
                    
                    # Создаем запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                        'title': entry.title[:200],
                        'description': full_text[:200] + '...' if len(full_text) > 200 else full_text,
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
                    
                    if images:
                        print(f"    ✅ СОХРАНЕНО | Текст: {len(full_text)} символов | Картинок: {len(images)}")
                    else:
                        print(f"    ✅ СОХРАНЕНО | Текст: {len(full_text)} символов")
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if len(all_news) > 300:
        all_news = all_news[:300]
    
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