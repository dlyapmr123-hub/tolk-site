#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import time
import hashlib
import re
from datetime import datetime
import feedparser
import requests
from urllib.parse import urlparse

print("=== ЗАПУСК СКРИПТА С ИИ ===")

# ============ НАСТОЯЩЕЕ ИИ-ПЕРЕФРАЗИРОВАНИЕ ============
def ai_rewrite_text(text):
    """Переписывает текст через ИИ (бесплатное API)"""
    if not text or len(text) < 100:
        return text
    
    try:
        # Используем бесплатное API для перефразирования
        api_url = "https://api-inference.huggingface.co/models/tuner007/pegasus_paraphrase"
        
        response = requests.post(
            api_url,
            json={"inputs": text[:1000]},  # Ограничиваем длину
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict) and 'generated_text' in result[0]:
                    return result[0]['generated_text']
                elif isinstance(result[0], str):
                    return result[0]
    except Exception as e:
        print(f"      ⚠️ ИИ не сработал: {e}")
    
    # Если ИИ не сработал, возвращаем оригинал
    return text

# ============ ЗАГРУЗКА ПОЛНОЙ СТАТЬИ ============
def fetch_full_article(url):
    """Загружает полный текст статьи и все картинки"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None, []
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем мусор
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
            tag.decompose()
        
        # === ИЩЕМ ВСЕ КАРТИНКИ ===
        article_images = []
        
        # 1. Картинки из тегов img
        for img in soup.find_all('img'):
            if img.get('src'):
                src = img['src']
                # Пропускаем иконки и маленькие картинки
                if any(x in src.lower() for x in ['icon', 'logo', 'avatar', 'button']):
                    continue
                
                if src.startswith('//'):
                    src = 'https:' + src
                    article_images.append(src)
                elif src.startswith('http'):
                    article_images.append(src)
                elif src.startswith('/'):
                    parsed = urlparse(url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    article_images.append(src)
        
        # 2. Картинки из meta-тегов (Open Graph)
        for meta in soup.find_all('meta', property='og:image'):
            if meta.get('content'):
                article_images.append(meta['content'])
        
        # === ИЩЕМ ОСНОВНОЙ ТЕКСТ ===
        content = None
        
        # Селекторы для разных сайтов
        selectors = [
            '.topic-body__content', '.b-topic__content',
            '.article__text', '.article-text',
            '.text-content', '.news-content',
            '.post-content', '.entry-content',
            'article', '[itemprop="articleBody"]',
            '.material-content', '.news-body'
        ]
        
        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        # Если не нашли, собираем все параграфы
        if not content:
            paragraphs = soup.find_all('p')
            if paragraphs:
                text = '\n\n'.join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
                text = re.sub(r'\n\s*\n', '\n\n', text)
                text = re.sub(r' +', ' ', text)
                return text.strip(), list(dict.fromkeys(article_images))[:10]
        
        if content:
            text = content.get_text()
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r' +', ' ', text)
            return text.strip(), list(dict.fromkeys(article_images))[:10]
        
        return None, list(dict.fromkeys(article_images))[:10]
        
    except Exception as e:
        print(f"      ⚠️ Ошибка загрузки: {e}")
        return None, []

# ============ ИЗВЛЕЧЕНИЕ КАРТИНОК ИЗ RSS ============
def extract_images_from_entry(entry):
    """Извлекает картинки из RSS ленты"""
    images = []
    
    # Из media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    
    # Из enclosures
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if enclosure.get('type', '').startswith('image'):
                img_url = enclosure.get('href', enclosure.get('url'))
                if img_url:
                    images.append(img_url)
    
    # Из summary
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(summary, 'html.parser')
        for img in soup.find_all('img'):
            if img.get('src'):
                src = img['src']
                if src.startswith('//'):
                    src = 'https:' + src
                images.append(src)
    
    return list(dict.fromkeys(images))

# ============ FIREBASE ============
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    print("✅ Firebase загружен")
    
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase инициализирован")
    else:
        db = None
        print("⚠️ serviceAccountKey.json не найден")
except Exception as e:
    print(f"⚠️ Ошибка Firebase: {e}")
    db = None

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

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  🤖 НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
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
            print(f"📚 Загружено {len(old_news)} старых новостей")
        except:
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    continue
                
                for entry in feed.entries[:3]:  # По 3 новости с каждой ленты
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  ✅ {entry.title[:70]}...")
                    
                    # Получаем картинки из RSS
                    rss_images = extract_images_from_entry(entry)
                    
                    # Загружаем полную статью
                    full_text, article_images = fetch_full_article(entry.link)
                    
                    # Объединяем все картинки
                    all_images = list(dict.fromkeys(rss_images + article_images))
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    if description:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(description, 'html.parser')
                        description = soup.get_text()[:200]
                    
                    # Применяем ИИ к тексту
                    if full_text:
                        print(f"      🤖 ИИ обрабатывает текст...")
                        rewritten = ai_rewrite_text(full_text)
                        
                        # Разбиваем на абзацы
                        paragraphs = rewritten.split('\n\n')
                        content_html = ''
                        for p in paragraphs[:10]:  # Максимум 10 абзацев
                            if p.strip():
                                content_html += f'<p>{p.strip()}</p>\n'
                        
                        print(f"      ✅ Текст обработан: {len(content_html)} символов")
                    else:
                        content_html = f'<p>{description}</p>'
                        print(f"      ⚠️ Текст не найден, использую описание")
                    
                    # Создаём запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:150] + '...' if len(description) > 150 else description,
                        'content': content_html,
                        'category': category,
                        'images': all_images[:5],  # Максимум 5 картинок
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
                    # Сохраняем в Firebase
                    if db:
                        try:
                            db.collection('news').add(news_item)
                        except:
                            pass
                    
                    time.sleep(2)  # Задержка между запросами
                    
            except Exception as e:
                print(f"  ⚠️ Ошибка: {feed_url} - {e}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    # Статистика
    news_with_images = sum(1 for item in all_news if item.get('images'))
    news_with_text = sum(1 for item in all_news if len(item.get('content', '')) > 100)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ СБОРА:")
    print(f"   📊 Всего новостей: {len(all_news)}")
    print(f"   🆕 Добавлено новых: {new_count}")
    print(f"   🖼️ С картинками: {news_with_images}")
    print(f"   📝 С текстом: {news_with_text}")
    print(f"{'='*60}")

if __name__ == '__main__':
    fetch_and_save()