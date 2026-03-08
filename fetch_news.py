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

print("=== ЗАПУСК СКРИПТА С ИИ-ПЕРЕФРАЗИРОВАНИЕМ ===")

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
# Используем бесплатный API через прокси (OpenRouter)
USE_AI = True  # Включить/выключить ИИ
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"  # Бесплатная модель
AI_API_KEY = "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"  # Замените на ваш ключ с https://openrouter.ai/


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
    
    # Удаляем специфичный мусор с сайтов
    garbage_patterns = [
        r'Войти.*?Выйти',
        r'Реклама.*?Реклама',
        r'Подпишись.*?новости',
        r'Соглашение.*?terms',
        r'ООО.*?Видео',
        r'VK.*?vkvideo\.ru',
        r'12\+',
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

def extract_main_text(html_content, site_url):
    """Извлечение основного текста статьи"""
    if not html_content:
        return None
    
    # Пробуем найти текст в разных местах
    text = ""
    
    # Ищем article или main контент
    article_patterns = [
        r'<article[^>]*>(.*?)</article>',
        r'<main[^>]*>(.*?)</main>',
        r'<div[^>]*class="[^"]*article[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)</div>',
    ]
    
    for pattern in article_patterns:
        matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
        if matches:
            text = max(matches, key=len)
            break
    
    if not text:
        # Если не нашли article, берем body
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
        if body_match:
            text = body_match.group(1)
        else:
            text = html_content
    
    # Очищаем от скриптов и стилей
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<header.*?>.*?</header>', '', text, flags=re.DOTALL)
    text = re.sub(r'<footer.*?>.*?</footer>', '', text, flags=re.DOTALL)
    text = re.sub(r'<nav.*?>.*?</nav>', '', text, flags=re.DOTALL)
    text = re.sub(r'<aside.*?>.*?</aside>', '', text, flags=re.DOTALL)
    
    # Очищаем HTML теги
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Очищаем от мусора
    text = clean_text(text)
    
    # Берем первые 1000 символов для перефразирования
    if len(text) > 1000:
        # Ищем конец предложения
        text = text[:1000]
        last_dot = text.rfind('.')
        if last_dot > 500:
            text = text[:last_dot + 1]
    
    return text

def fetch_article_text(url):
    """Загружает текст статьи с очисткой"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        
        text = extract_main_text(response.text, url)
        return text
        
    except Exception as e:
        print(f"  Ошибка загрузки {url}: {e}")
        return None

def ai_rewrite_text(text, title, category):
    """Перефразирование текста через ИИ"""
    if not text or len(text) < 100:
        return None
    
    if not USE_AI:
        return create_fallback_text(text, title, category)
    
    try:
        # Промпт для ИИ
        prompt = f"""Перепиши эту новость своими словами, сохранив смысл. 
Убери лишнюю информацию, рекламу, ссылки. 
Напиши кратко, но информативно (3-5 предложений).

Категория: {category}
Заголовок: {title}
Текст: {text}

Твой переписанный текст (только сам текст, без пояснений):"""

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Для OpenRouter
        data = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 300
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if "choices" in result:
                rewritten = result["choices"][0]["message"]["content"]
            else:
                rewritten = result.get("candidates", [{}])[0].get("content", "")
            
            # Очищаем результат
            rewritten = clean_text(rewritten)
            
            # Если получили нормальный текст, возвращаем
            if len(rewritten) > 50:
                return rewritten
        
        # Если ИИ не сработал, используем fallback
        return create_fallback_text(text, title, category)
        
    except Exception as e:
        print(f"  Ошибка ИИ: {e}")
        return create_fallback_text(text, title, category)

def create_fallback_text(text, title, category):
    """Создание текста без ИИ (упрощенное перефразирование)"""
    if not text:
        return f"<p>Новость из категории {category}: {title}</p>"
    
    # Берем первые 2-3 предложения
    sentences = re.split(r'[.!?]+', text)
    good_sentences = []
    
    for s in sentences:
        s = s.strip()
        if len(s) > 30 and not any(x in s.lower() for x in ['реклама', 'подпишись', 'vk.com', 'telegram']):
            good_sentences.append(s)
        if len(good_sentences) >= 3:
            break
    
    if good_sentences:
        result = '. '.join(good_sentences) + '.'
    else:
        result = text[:300] + "..."
    
    return result

def extract_images_from_entry(entry, full_html=None):
    """Улучшенное извлечение картинок"""
    images = []
    
    # Из media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                url = media['url']
                if not url.startswith('http'):
                    url = 'https:' + url
                images.append(url)
    
    # Из media:thumbnail
    if hasattr(entry, 'media_thumbnail'):
        for thumb in entry.media_thumbnail:
            if thumb.get('url'):
                url = thumb['url']
                if not url.startswith('http'):
                    url = 'https:' + url
                images.append(url)
    
    # Из summary
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        img_urls = re.findall(r'<img[^>]+src="([^">]+)"', summary)
        for url in img_urls:
            if not url.startswith('http'):
                url = 'https:' + url
            images.append(url)
    
    # Из полного HTML, если есть
    if full_html:
        img_urls = re.findall(r'<img[^>]+src="([^">]+)"', full_html)
        for url in img_urls:
            if not url.startswith('http'):
                url = 'https:' + url
            if 'logo' not in url.lower() and 'icon' not in url.lower():
                images.append(url)
    
    # Фильтруем и убираем дубликаты
    seen = set()
    unique = []
    
    for img in images:
        # Убираем параметры из URL
        base_url = img.split('?')[0]
        if base_url not in seen:
            # Проверяем, что это похоже на картинку новости
            if any(x in base_url.lower() for x in ['.jpg', '.jpeg', '.png', '.webp', '/photo', '/image', '/picture']):
                seen.add(base_url)
                unique.append(img)
            elif len(unique) < 2:  # Если мало картинок, берем любые
                seen.add(base_url)
                unique.append(img)
    
    return unique[:MAX_IMAGES]

def extract_description(entry):
    """Извлечение описания"""
    # Пробуем разные поля
    description = (entry.get('summary', '') or 
                  entry.get('description', '') or 
                  entry.get('title', ''))
    
    # Очищаем
    description = re.sub(r'<[^>]+>', '', description)
    description = clean_text(description)
    
    # Берем первые 200 символов
    if len(description) > 200:
        description = description[:200] + '...'
    
    return description

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    json_path = 'public/news_data_v3.json'
    version_path = 'public/version.json'
    
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
    total_processed = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 {category}")
        
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Нет записей: {feed_url.split('/')[-1]}")
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  🔍 {entry.title[:70]}...")
                    
                    # Загружаем полный текст
                    full_text = fetch_article_text(entry.link)
                    
                    # Получаем описание
                    description = extract_description(entry)
                    
                    # Перефразируем текст через ИИ
                    if full_text:
                        rewritten = ai_rewrite_text(full_text, entry.title, category)
                        if rewritten:
                            # Разбиваем на абзацы
                            sentences = rewritten.split('. ')
                            content_html = ''
                            for i, sent in enumerate(sentences[:5]):
                                if sent.strip():
                                    content_html += f'<p>{sent.strip()}.</p>\n'
                        else:
                            content_html = f'<p>{description}</p>'
                    else:
                        content_html = f'<p>{description}</p>'
                    
                    # Получаем картинки
                    images = extract_images_from_entry(entry, full_text)
                    
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
                    print(f"    ✅ Добавлено (картинок: {len(images)})")
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"  ❌ Ошибка: {feed_url} - {e}")
                continue
    
    # Сортируем по дате
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Оставляем только последние 200
    if len(all_news) > 200:
        all_news = all_news[:200]
    
    # Сохраняем JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    # Сохраняем версию
    version_data = {
        'version': datetime.now().timestamp(),
        'updated': datetime.now().isoformat(),
        'count': len(all_news),
        'new': new_count,
        'processed': total_processed
    }
    
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"   Всего обработано: {total_processed}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"   Без текста: {sum(1 for item in all_news if not item.get('content'))}")
    print(f"{'='*60}")

if __name__ == '__main__':
    fetch_and_save()