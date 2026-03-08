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
TIMEOUT = 10
MAX_ARTICLES_PER_FEED = 3
REQUEST_DELAY = 1
MAX_IMAGES = 3

# ============ RSS ИСТОЧНИКИ (ТОЛЬКО БЫСТРЫЕ) ============
RSS_FEEDS = {
    'Политика': [
        'https://ria.ru/export/rss2/politics/index.xml',
    ],
    'Экономика': [
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://www.rbc.ru/rss/',
    ],
    'Технологии': [
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://habr.com/ru/rss/news/?fl=ru',
    ],
    'Авто': [
        'https://ria.ru/export/rss2/auto/index.xml',
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
    ],
    'Культура': [
        'https://ria.ru/export/rss2/culture/index.xml',
    ],
    'Спорт': [
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://www.championat.com/news/rss/',
    ]
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

print(f"📊 Настройки: TIMEOUT={TIMEOUT}, MAX_ARTICLES={MAX_ARTICLES_PER_FEED}")
print(f"🤖 ИИ: {'ВКЛЮЧЕН' if USE_AI else 'ВЫКЛЮЧЕН'}")
print(f"📡 Источников: {sum(len(feeds) for feeds in RSS_FEEDS.values())}")
print("=" * 60)

def clean_text(text):
    """Быстрая очистка текста от мусора"""
    if not text:
        return ""
    
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Декодируем HTML сущности
    text = html.unescape(text)
    
    # Удаляем лишние пробелы и переносы
    text = re.sub(r'\s+', ' ', text)
    
    # Короткий список мусора для быстрой очистки
    garbage_phrases = [
        'реклама', 'подпишись', 'telegram', 'vk', 'вконтакте', 
        'youtube', 'instagram', 'cookie', 'читать далее', 
        'фото:', 'видео:', 'смотрите также', 'по теме',
        'все права защищены', 'источник:', 'ссылка:',
        'наверх', 'показать полностью'
    ]
    
    for phrase in garbage_phrases:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    
    # Убираем множественные точки и пробелы
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_text_fast(html_content):
    """Быстрое извлечение текста и картинок"""
    if not html_content:
        return None, []
    
    images = []
    
    try:
        # Ищем картинки
        img_matches = re.findall(r'<img[^>]+src="([^">]+)"', html_content)
        for url in img_matches[:MAX_IMAGES * 2]:  # Ищем больше для фильтрации
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                # Относительный путь пропускаем
                continue
            
            # Проверяем, что это реальная картинка, а не иконка
            if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', url.lower()):
                if not re.search(r'(logo|icon|avatar|favicon|pixel|spacer|button|banner|ad|reklama)', url.lower()):
                    images.append(url)
        
        # Ищем текст в параграфах
        p_matches = re.findall(r'<p[^>]*>(.*?)</p>', html_content, re.DOTALL)
        text_parts = []
        
        for p in p_matches[:8]:
            p_text = re.sub(r'<[^>]+>', ' ', p)
            p_text = html.unescape(p_text)
            p_text = re.sub(r'\s+', ' ', p_text).strip()
            
            if len(p_text) > 40 and not re.search(r'(реклама|подпишись|vk|telegram)', p_text.lower()):
                text_parts.append(p_text)
        
        if text_parts:
            full_text = ' '.join(text_parts)
            full_text = clean_text(full_text)
            
            # Убираем дубликаты картинок
            unique_images = []
            seen = set()
            for img in images:
                base_url = img.split('?')[0]
                if base_url not in seen:
                    seen.add(base_url)
                    unique_images.append(img)
            
            return full_text, unique_images[:MAX_IMAGES]
        
        return None, images[:MAX_IMAGES]
        
    except Exception as e:
        return None, images[:MAX_IMAGES]

def fetch_article_data(url):
    """Загрузка статьи и картинок"""
    try:
        print(f"    📥 Загрузка: {url[:50]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code != 200:
            return None, []
        
        if len(response.text) < 2000:
            return None, []
        
        text, images = extract_text_fast(response.text)
        
        if text and len(text) > 200:
            return text, images
        else:
            return None, images
        
    except requests.exceptions.Timeout:
        return None, []
    except Exception as e:
        return None, []

def ai_rewrite_text(text, title, category):
    """Перефразирование текста через ИИ"""
    if not text or len(text) < 200 or not USE_AI:
        return text
    
    try:
        print(f"    🤖 ИИ обрабатывает текст...")
        
        short_text = text[:800]
        
        prompt = f"""Перепиши эту новость своими словами, сохранив смысл.
Напиши кратко, 3-4 предложения, без рекламы и лишней информации.

Категория: {category}
Заголовок: {title}

Текст: {short_text}

Переписанный текст:"""
        
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tolk-1.web.app",
            "X-Title": "Tolk News"
        }
        
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
            rewritten = clean_text(rewritten)
            
            if len(rewritten) > 100:
                return rewritten
        
        return text
        
    except Exception as e:
        return text

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now().strftime('%H:%M:%S')}]")
    print(f"{'='*60}")
    
    # Создаем папку public
    if not os.path.exists('public'):
        os.makedirs('public')
    
    json_path = 'public/news_data_v3.json'
    version_path = 'public/version.json'
    
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
        except Exception as e:
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    total_processed = 0
    skipped_no_images = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category} ({len(feeds)} источников)")
        
        for feed_url in feeds:
            try:
                print(f"  📰 RSS: {feed_url.split('/')[-1]}")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Нет записей")
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 {entry.title[:60]}...")
                    
                    # Загружаем текст и картинки
                    full_text, images = fetch_article_data(entry.link)
                    
                    # ПРОВЕРКА: если нет картинок - пропускаем
                    if not images or len(images) == 0:
                        print(f"    ⚠️ ПРОПУЩЕНО: нет картинок")
                        skipped_no_images += 1
                        continue
                    
                    if not full_text:
                        full_text = entry.get('summary', '') or entry.get('description', '')
                        full_text = re.sub(r'<[^>]+>', '', full_text)
                        full_text = clean_text(full_text)
                    
                    # Применяем ИИ
                    if USE_AI and full_text:
                        full_text = ai_rewrite_text(full_text, entry.title, category)
                    
                    # Форматируем текст
                    if full_text:
                        sentences = re.split(r'[.!?]+', full_text)
                        content_html = ''
                        for i, sent in enumerate(sentences[:5]):
                            sent = sent.strip()
                            if sent:
                                content_html += f'<p>{sent}.</p>\n'
                    else:
                        content_html = f'<p>{entry.title}</p>'
                    
                    description = full_text[:150] + '...' if full_text and len(full_text) > 150 else (full_text or entry.title)
                    
                    # Создаем запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                        'title': entry.title[:150],
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
                    
                    print(f"    ✅ СОХРАНЕНО | Картинок: {len(images)}")
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if len(all_news) > 200:
        all_news = all_news[:200]
    
    # Сохраняем JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON сохранен: {json_path}")
    
    # Сохраняем версию
    version_data = {
        'version': datetime.now().timestamp(),
        'updated': datetime.now().isoformat(),
        'total': len(all_news),
        'new': new_count,
        'processed': total_processed,
        'skipped_no_images': skipped_no_images,
        'with_images': sum(1 for item in all_news if item.get('images'))
    }
    
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Version сохранен: {version_path}")
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ РАБОТЫ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"   Всего обработано: {total_processed}")
    print(f"   Пропущено (нет картинок): {skipped_no_images}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)