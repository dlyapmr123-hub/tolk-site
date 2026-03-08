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
print("=== СБОР НОВОСТЕЙ (ПРАВИЛЬНЫЙ ПАРСИНГ RSS) ===")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ============ НАСТРОЙКИ ============
MAX_ARTICLES_PER_FEED = 30

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

print(f"✅ API ключ загружен, ИИ активен")

def debug_print(obj, name):
    """Отладочная печать структуры объекта"""
    print(f"\n--- DEBUG: {name} ---")
    if hasattr(obj, 'keys'):
        for key in obj.keys():
            print(f"  {key}: {type(obj[key])}")
    elif hasattr(obj, '__dict__'):
        for key in obj.__dict__:
            print(f"  {key}: {type(getattr(obj, key))}")
    print("-------------------")

def get_full_text_from_entry(entry):
    """Извлекаем ПОЛНЫЙ текст из записи RSS"""
    
    print(f"\n    🔍 Ищем текст в entry...")
    
    # 1. Пробуем content:encoded (там чаще всего полный текст)
    if hasattr(entry, 'content'):
        for content in entry.content:
            if content.get('type') == 'text/html' or content.get('type') == 'text/plain':
                if content.get('value'):
                    text = content['value']
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = html.unescape(text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if len(text) > 200:
                        print(f"      ✅ Нашли текст в content: {len(text)} символов")
                        return text
    
    # 2. Пробуем content:encoded (альтернативный формат)
    if hasattr(entry, 'content_encoded'):
        text = entry.content_encoded
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            print(f"      ✅ Нашли текст в content_encoded: {len(text)} символов")
            return text
    
    # 3. Пробуем summary_detail
    if hasattr(entry, 'summary_detail'):
        if hasattr(entry.summary_detail, 'value'):
            text = entry.summary_detail.value
            text = re.sub(r'<[^>]+>', ' ', text)
            text = html.unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 200:
                print(f"      ✅ Нашли текст в summary_detail: {len(text)} символов")
                return text
    
    # 4. Пробуем description
    if hasattr(entry, 'description'):
        text = entry.description
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            print(f"      ✅ Нашли текст в description: {len(text)} символов")
            return text
    
    # 5. Пробуем summary
    if hasattr(entry, 'summary'):
        text = entry.summary
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            print(f"      ✅ Нашли текст в summary: {len(text)} символов")
            return text
    
    print(f"      ❌ Текст не найден ни в одном поле")
    
    # Отладочная информация
    print(f"    Доступные поля: {dir(entry)}")
    if hasattr(entry, 'keys'):
        print(f"    Ключи: {entry.keys()}")
    
    return None

def clean_article_text(text):
    """Очистка текста статьи от мусора"""
    if not text:
        return ""
    
    # Удаляем "Читайте также" и похожие блоки
    text = re.sub(r'Читайте также:.*?(?=\n|$)', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Фото:.*?(?=\n|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Видео:.*?(?=\n|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Смотрите также:.*?(?=\n|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'По теме:.*?(?=\n|$)', '', text, flags=re.IGNORECASE)
    
    # Удаляем ссылки
    text = re.sub(r'https?://\S+', '', text)
    
    # Удаляем теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Очищаем пробелы
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def ai_rewrite_text(text, title):
    """Переписывание текста через ИИ"""
    if not text or len(text) < 200 or not USE_AI:
        return text
    
    try:
        print(f"    🤖 ИИ обрабатывает текст...")
        
        prompt = f"""Перепиши эту новость своими словами. Сохрани все важные факты.
Напиши связный текст из 4-6 предложений. Убери рекламу и лишнее.

Заголовок: {title}

Текст: {text[:1500]}

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
            "max_tokens": 800
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"]
            rewritten = re.sub(r'\s+', ' ', rewritten).strip()
            print(f"      ✅ ИИ обработал: {len(rewritten)} символов")
            return rewritten
        
        return text
    except Exception as e:
        print(f"      ⚠️ Ошибка ИИ: {e}")
        return text

def get_image_from_entry(entry):
    """Ищем картинку в записи"""
    images = []
    
    # Ищем в media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                url = media['url']
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
    
    # Ищем в links
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                images.append(link.get('href'))
    
    # Ищем в summary
    if hasattr(entry, 'summary'):
        img_match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
        if img_match:
            url = img_match.group(1)
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
    total_processed = 0
    
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
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 [{i+1}] {entry.title[:60]}...")
                    
                    # Получаем ПОЛНЫЙ текст
                    full_text = get_full_text_from_entry(entry)
                    
                    if not full_text:
                        print(f"    ❌ Пропускаем - нет текста")
                        continue
                    
                    # Очищаем текст
                    full_text = clean_article_text(full_text)
                    
                    # Применяем ИИ
                    if USE_AI and len(full_text) > 300:
                        rewritten = ai_rewrite_text(full_text, entry.title)
                        if rewritten and len(rewritten) > 100:
                            full_text = rewritten
                    
                    # Получаем картинки
                    images = get_image_from_entry(entry)
                    
                    # Форматируем текст в параграфы
                    paragraphs = full_text.split('. ')
                    content_html = ''
                    for p in paragraphs[:8]:
                        if p.strip():
                            content_html += f'<p>{p.strip()}.</p>\n'
                    
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
                    
                    print(f"    ✅ СОХРАНЕНО | Текст: {len(full_text)} символов | Картинок: {len(images)}")
                    
                    time.sleep(0.5)
                    
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
    print(f"   Всего обработано: {total_processed}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()