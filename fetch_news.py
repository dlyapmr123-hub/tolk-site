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
TIMEOUT = 15
MAX_ARTICLES_PER_FEED = 30
REQUEST_DELAY = 1
MAX_IMAGES = 3
MIN_TEXT_LENGTH = 300

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': [
        'https://ria.ru/export/rss2/politics/index.xml',
        'https://tass.ru/rss/v2.xml',
    ],
    'Экономика': [
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://tass.ru/rss/v2.xml',
    ],
    'Технологии': [
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://tass.ru/rss/v2.xml',
    ],
    'Авто': [
        'https://ria.ru/export/rss2/auto/index.xml',
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
    ],
    'Культура': [
        'https://ria.ru/export/rss2/culture/index.xml',
        'https://tass.ru/rss/v2.xml',
    ],
    'Спорт': [
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://tass.ru/rss/v2.xml',
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
print("=" * 60)

def clean_text(text):
    """Очистка текста от мусора"""
    if not text:
        return ""
    
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Декодируем HTML сущности
    text = html.unescape(text)
    
    # Удаляем лишние пробелы и переносы
    text = re.sub(r'\s+', ' ', text)
    
    # Удаляем "Читайте также" и похожие блоки
    text = re.sub(r'Читайте также:.*?(?=\.|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'По теме:.*?(?=\.|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Смотрите также:.*?(?=\.|$)', '', text, flags=re.IGNORECASE)
    
    # Удаляем ссылки на соцсети
    text = re.sub(r'Telegram|VK|Вконтакте|YouTube|Instagram|Twitter|Facebook', '', text, flags=re.IGNORECASE)
    
    # Удаляем копирайты
    text = re.sub(r'©.*?\d{4}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Все права защищены', '', text, flags=re.IGNORECASE)
    
    # Убираем множественные точки
    text = re.sub(r'\.{3,}', '.', text)
    text = re.sub(r'\.{2,}', '.', text)
    
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_full_text(html_content, url):
    """Извлечение ПОЛНОГО текста статьи"""
    if not html_content:
        return None, []
    
    images = []
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Удаляем ненужные элементы
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
            tag.decompose()
        
        # Удаляем блоки с рекламой и навигацией
        for class_name in ['ad', 'ads', 'advertisement', 'banner', 'promo', 'subscribe', 
                          'menu', 'navigation', 'navbar', 'sidebar', 'comments', 
                          'share', 'social', 'tags', 'related', 'popular', 'news-list']:
            for element in soup.find_all(class_=re.compile(class_name, re.I)):
                element.decompose()
        
        # Ищем картинки
        for img in soup.find_all('img'):
            img_url = img.get('src') or img.get('data-src') or img.get('data-original')
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    parsed = urlparse(url)
                    img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
                
                if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', img_url.lower()):
                    if not re.search(r'(logo|icon|avatar|favicon|pixel|spacer|button|banner|ad)', img_url.lower()):
                        images.append(img_url)
        
        # Ищем статью
        article = None
        article = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'article|post|content|text|story|news-body', re.I))
        
        if not article:
            article = soup.find('body')
        
        if not article:
            return None, images[:MAX_IMAGES]
        
        # СОБИРАЕМ ВСЕ ПАРАГРАФЫ
        paragraphs = article.find_all('p')
        text_parts = []
        
        for p in paragraphs:
            p_text = p.get_text(strip=True)
            
            # Пропускаем слишком короткие параграфы
            if len(p_text) < 30:
                continue
            
            # Пропускаем явную рекламу
            if re.search(r'(реклама|подпишись|telegram|vk|вконтакте)', p_text.lower()):
                continue
            
            # Пропускаем "Читайте также"
            if re.search(r'читайте также|по теме|смотрите также', p_text.lower()):
                continue
            
            text_parts.append(p_text)
        
        if text_parts:
            full_text = ' '.join(text_parts)
            full_text = clean_text(full_text)
            
            # Проверяем длину
            if len(full_text) < MIN_TEXT_LENGTH:
                print(f"      ⚠️ Текст слишком короткий: {len(full_text)} символов")
                # Возвращаем то что есть, но с предупреждением
                return full_text, images[:MAX_IMAGES]
            
            # Убираем дубликаты картинок
            unique_images = []
            seen = set()
            for img in images:
                if img not in seen:
                    seen.add(img)
                    unique_images.append(img)
            
            print(f"      📝 Найдено текста: {len(full_text)} символов ({len(text_parts)} параграфов)")
            return full_text, unique_images[:MAX_IMAGES]
        
        # Если нет параграфов, берем весь текст
        full_text = article.get_text(separator=' ', strip=True)
        full_text = clean_text(full_text)
        
        if len(full_text) > MIN_TEXT_LENGTH:
            return full_text, images[:MAX_IMAGES]
        
        return None, images[:MAX_IMAGES]
        
    except Exception as e:
        print(f"      ❌ Ошибка парсинга: {e}")
        return None, images[:MAX_IMAGES]

def fetch_article_data(url):
    """Загрузка ПОЛНОЙ статьи"""
    try:
        print(f"    📥 Загрузка: {url[:50]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        
        if response.status_code != 200:
            return None, []
        
        # Извлекаем полный текст
        text, images = extract_full_text(response.text, url)
        
        if text:
            return text, images
        else:
            return None, images
        
    except Exception as e:
        return None, []

def ai_rewrite_text(text, title, category):
    """Перефразирование текста через ИИ"""
    if not text or len(text) < 300 or not USE_AI:
        return text
    
    try:
        print(f"    🤖 ИИ обрабатывает текст...")
        
        # Берем текст для ИИ
        text_for_ai = text[:2500] if len(text) > 2500 else text
        
        prompt = f"""Перепиши эту новость полностью своими словами, сохранив все факты.
Напиши связный текст из 4-6 предложений.
Убери рекламу и лишнюю информацию.

Категория: {category}
Заголовок: {title}

Текст: {text_for_ai}

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
            "max_tokens": 800
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"]
            rewritten = clean_text(rewritten)
            
            if len(rewritten) > 150:
                print(f"    ✅ ИИ обработал, {len(rewritten)} символов")
                return rewritten
        
        return text
        
    except Exception as e:
        return text

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now().strftime('%H:%M:%S')}]")
    print(f"{'='*60}")
    
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
    skipped_already_exists = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category} ({len(feeds)} источников)")
        
        for feed_url in feeds:
            try:
                print(f"  📰 RSS: {feed_url.split('/')[-1]}")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Нет записей")
                    continue
                
                entries_count = len(feed.entries)
                print(f"  📊 Найдено записей: {entries_count}")
                
                for i, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_FEED], 1):
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        skipped_already_exists += 1
                        continue
                    
                    print(f"\n  🔍 [{i}/{MAX_ARTICLES_PER_FEED}] {entry.title[:60]}...")
                    
                    # Загружаем полный текст
                    full_text, images = fetch_article_data(entry.link)
                    
                    # Если не загрузилось, используем RSS
                    if not full_text:
                        print(f"    ⚠️ Использую RSS")
                        full_text = entry.get('summary', '') or entry.get('description', '')
                        full_text = re.sub(r'<[^>]+>', '', full_text)
                        full_text = clean_text(full_text)
                    
                    # Применяем ИИ
                    if USE_AI and full_text and len(full_text) > 200:
                        full_text = ai_rewrite_text(full_text, entry.title, category)
                    
                    # Форматируем текст
                    if full_text:
                        # Разбиваем на абзацы
                        paragraphs = full_text.split('. ')
                        content_html = ''
                        for p in paragraphs:
                            if p.strip():
                                content_html += f'<p>{p.strip()}.</p>\n'
                    else:
                        content_html = f'<p>{entry.title}</p>'
                    
                    # Создаем запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                        'title': entry.title[:200],
                        'description': full_text[:200] + '...' if full_text and len(full_text) > 200 else full_text,
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
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    if len(all_news) > 300:
        all_news = all_news[:300]
    
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
        'skipped_already_exists': skipped_already_exists,
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
    print(f"   Пропущено (уже есть): {skipped_already_exists}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)