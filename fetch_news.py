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
import random
import sys
import traceback

# Принудительно включаем вывод в реальном времени
try:
    sys.stdout.reconfigure(line_buffering=True)
except:
    pass  # Для старых версий Python

print("=" * 60)
print("=== ЗАПУСК СКРИПТА С ПОЛНЫМ ТЕКСТОМ И ИИ ===")
print(f"Python version: {sys.version}")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Рабочая директория: {os.getcwd()}")
print("=" * 60)

# Пытаемся импортировать BeautifulSoup
try:
    from bs4 import BeautifulSoup
    print("✅ BeautifulSoup импортирован успешно")
except ImportError as e:
    print(f"❌ Ошибка импорта BeautifulSoup: {e}")
    print("Пытаемся установить beautifulsoup4 и lxml...")
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4", "lxml"])
        from bs4 import BeautifulSoup
        print("✅ BeautifulSoup установлен и импортирован")
    except Exception as install_error:
        print(f"❌ Не удалось установить BeautifulSoup: {install_error}")
        print("Продолжаем без BeautifulSoup (упрощенный режим)")
        BeautifulSoup = None

# ============ НАСТРОЙКИ ============
TIMEOUT = 15
MAX_ARTICLES_PER_FEED = 3
REQUEST_DELAY = 3
MAX_IMAGES = 3

# ============ RSS ИСТОЧНИКИ ============
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

# ============ НАСТРОЙКИ ИИ ============
USE_AI = False  # Отключаем ИИ для начала, пока не настроим ключ
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"
AI_API_KEY = "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"  # Оставляем пустым, ИИ будет отключен

print(f"📊 Настройки: TIMEOUT={TIMEOUT}, MAX_ARTICLES={MAX_ARTICLES_PER_FEED}")
print(f"🤖 ИИ: {'ВКЛЮЧЕН' if USE_AI else 'ВЫКЛЮЧЕН'}")
print("=" * 60)

def clean_text(text):
    """Полная очистка текста от мусора"""
    if not text:
        return ""
    
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Декодируем HTML сущности
    text = html.unescape(text)
    
    # Удаляем лишние пробелы и переносы
    text = re.sub(r'\s+', ' ', text)
    
    # Удаляем специфичный мусор с сайтов
    garbage_patterns = [
        r'Главное.*?Мир',
        r'Бывший СССР',
        r'Силовые структуры',
        r'Наука и техника',
        r'Интернет и СМИ',
        r'Ценности',
        r'Путешествия',
        r'Из жизни',
        r'Среда обитания',
        r'Забота о себе',
        r'Теперь вы знаете',
        r'Войти',
        r'Эксклюзивы',
        r'Статьи',
        r'Галереи',
        r'Видео',
        r'Спецпроекты',
        r'Исследования',
        r'Мини-игры',
        r'Архив',
        r'Лента добра',
        r'Хочешь видеть только хорошие новости\?.*?Жми!',
        r'Вернуться в обычную ленту\?',
        r'Реклама.*?Реклама',
        r'Подпишись.*?новости',
        r'Соглашение.*?terms',
        r'ООО.*?Видео',
        r'VK.*?vkvideo\.ru',
        r'12\+',
        r'Читайте также:.*?(?=\.|$)',
        r'Фото:.*?(?=\.|$)',
        r'Видео:.*?(?=\.|$)',
        r'©.*?\d{4}',
        r'Все права защищены',
        r'Источник:.*?(?=\.|$)',
        r'Ссылка:.*?(?=\.|$)',
    ]
    
    for pattern in garbage_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Убираем множественные точки и пробелы
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_main_text_simple(html_content):
    """Упрощенное извлечение текста без BeautifulSoup"""
    if not html_content:
        return None
    
    # Удаляем скрипты и стили
    html_content = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'<style.*?>.*?</style>', '', html_content, flags=re.DOTALL)
    
    # Удаляем все теги
    text = re.sub(r'<[^>]+>', ' ', html_content)
    
    # Очищаем
    text = clean_text(text)
    
    # Ищем предложения
    sentences = re.split(r'[.!?]+', text)
    good_sentences = []
    
    for s in sentences:
        s = s.strip()
        if len(s) > 50 and not re.search(r'(реклама|подпишись|vk|telegram)', s.lower()):
            good_sentences.append(s)
        if len(good_sentences) >= 5:
            break
    
    if good_sentences:
        return '. '.join(good_sentences) + '.'
    
    return text[:1000]

def extract_main_text_bs4(html_content, site_url):
    """Извлечение текста с BeautifulSoup"""
    if not html_content or not BeautifulSoup:
        return extract_main_text_simple(html_content)
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Удаляем скрипты, стили, навигацию
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        
        # Ищем статью
        article = None
        article = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'article|post|content|text|story', re.I))
        
        if not article:
            article = soup.find('body')
        
        if not article:
            return extract_main_text_simple(html_content)
        
        # Собираем параграфы
        paragraphs = article.find_all('p')
        text_parts = []
        
        for p in paragraphs[:10]:  # Первые 10 параграфов
            p_text = p.get_text(strip=True)
            if len(p_text) > 30 and not re.search(r'(реклама|подпишись)', p_text.lower()):
                text_parts.append(p_text)
        
        if text_parts:
            return ' '.join(text_parts)
        
        return extract_main_text_simple(str(article))
        
    except Exception as e:
        print(f"    ⚠️ Ошибка BeautifulSoup: {e}")
        return extract_main_text_simple(html_content)

def fetch_article_text(url):
    """Загружает текст статьи"""
    try:
        print(f"    📥 Загрузка: {url[:60]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            print(f"    ❌ Ошибка HTTP: {response.status_code}")
            return None
        
        # Извлекаем текст
        if BeautifulSoup:
            text = extract_main_text_bs4(response.text, url)
        else:
            text = extract_main_text_simple(response.text)
        
        if text and len(text) > 100:
            print(f"    ✅ Загружено {len(text)} символов")
            return text
        else:
            print(f"    ⚠️ Текст слишком короткий: {len(text) if text else 0}")
            return None
        
    except Exception as e:
        print(f"    ❌ Ошибка загрузки: {e}")
        return None

def extract_images_from_entry(entry, full_html=None):
    """Извлечение картинок"""
    images = []
    
    # Из RSS
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                url = media['url']
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
    
    # Из summary
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        img_urls = re.findall(r'<img[^>]+src="([^">]+)"', summary)
        for url in img_urls:
            if url.startswith('//'):
                url = 'https:' + url
            images.append(url)
    
    # Убираем дубликаты
    seen = set()
    unique = []
    for img in images:
        base_url = img.split('?')[0]
        if base_url not in seen and re.search(r'\.(jpg|jpeg|png|webp)(\?|$)', base_url.lower()):
            seen.add(base_url)
            unique.append(img)
    
    return unique[:MAX_IMAGES]

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    # Создаем папку public если её нет
    if not os.path.exists('public'):
        print("📁 Создаем папку public...")
        os.makedirs('public')
    
    json_path = 'public/news_data_v3.json'
    version_path = 'public/version.json'
    
    print(f"📄 JSON файл: {json_path}")
    
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
            print(f"📊 Загружено {len(old_news)} старых новостей")
            print(f"📊 Существующих ссылок: {len(existing_links)}")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки старого JSON: {e}")
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    total_processed = 0
    failed = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 КАТЕГОРИЯ: {category} ({len(feeds)} источников)")
        
        for feed_url in feeds:
            try:
                print(f"  📰 RSS: {feed_url}")
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Нет записей")
                    continue
                
                print(f"  📊 Найдено записей: {len(feed.entries)}")
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 НОВОСТЬ: {entry.title[:80]}...")
                    
                    # Загружаем текст
                    full_text = fetch_article_text(entry.link)
                    
                    if not full_text:
                        failed += 1
                        continue
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    description = re.sub(r'<[^>]+>', '', description)
                    description = clean_text(description)[:200]
                    
                    # Форматируем текст в HTML
                    paragraphs = full_text.split('. ')
                    content_html = ''
                    for i, sent in enumerate(paragraphs[:5]):
                        if sent.strip():
                            content_html += f'<p>{sent.strip()}.</p>\n'
                    
                    # Получаем картинки
                    images = extract_images_from_entry(entry)
                    
                    # Создаём запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:150] + '...' if len(description) > 150 else description,
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
                    
                    print(f"    ✅ СОХРАНЕНО | Картинок: {len(images)} | Текст: {len(full_text)} символов")
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                failed += 1
                continue
    
    # Сортируем по дате
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Оставляем последние 200
    if len(all_news) > 200:
        all_news = all_news[:200]
    
    # Сохраняем JSON
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_news, f, ensure_ascii=False, indent=2)
        print(f"\n✅ JSON сохранен: {json_path}")
    except Exception as e:
        print(f"❌ Ошибка сохранения JSON: {e}")
    
    # Сохраняем версию
    version_data = {
        'version': datetime.now().timestamp(),
        'updated': datetime.now().isoformat(),
        'total': len(all_news),
        'new': new_count,
        'processed': total_processed,
        'failed': failed
    }
    
    try:
        with open(version_path, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Version сохранен: {version_path}")
    except Exception as e:
        print(f"❌ Ошибка сохранения version: {e}")
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ РАБОТЫ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"   Всего обработано: {total_processed}")
    print(f"   Не удалось загрузить: {failed}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)