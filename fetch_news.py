# fetch_news.py
import feedparser
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import hashlib
import random
import requests
from urllib.parse import urlparse
import re
import os
import firebase_admin
from firebase_admin import credentials, firestore

# ============ НАСТРОЙКИ ============
TIMEOUT = 5  # Таймаут 5 секунд (оптимально)
MAX_ARTICLES_PER_FEED = 3  # По 3 статьи с каждой ленты
MAX_PARAGRAPHS = 5  # По 5 абзацев на статью
REQUEST_DELAY = 1  # Задержка между запросами 1 секунда

# Инициализация Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ============ RSS ИСТОЧНИКИ (РАСШИРЕННЫЕ) ============
RSS_FEEDS = {
    'Политика': [
        'https://lenta.ru/rss/news/politics',
        'https://ria.ru/export/rss2/politics/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://rg.ru/xml/index.xml'
    ],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://www.rbc.ru/rss/',
        'https://1prime.ru/feed/rss/'
    ],
    'Технологии': [
        'https://lenta.ru/rss/news/technology',
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://habr.com/ru/rss/news/?fl=ru',
        'https://3dnews.ru/news/rss/'
    ],
    'Авто': [
        'https://lenta.ru/rss/news/auto',
        'https://motor.ru/rss',
        'https://www.autonews.ru/export/rss2/news/index.xml',
        'https://www.zr.ru/content/news/rss/'
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
        'https://stopgame.ru/rss/news.xml',
        'https://gameguru.ru/rss/news.xml',
        'https://www.goha.ru/rss/news'
    ],
    'Культура': [
        'https://lenta.ru/rss/news/art',
        'https://ria.ru/export/rss2/culture/index.xml',
        'https://www.mk.ru/rss/culture/index.xml',
        'https://tvkultura.ru/rss/news.xml'
    ],
    'Спорт': [
        'https://lenta.ru/rss/news/sport',
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://www.championat.com/news/rss/',
        'https://news.sportbox.ru/rss'
    ]
}

def extract_images_from_entry(entry):
    """Извлечение картинок из RSS записи"""
    images = []
    
    # Из media_content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    
    # Из summary
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        soup = BeautifulSoup(summary, 'html.parser')
        for img in soup.find_all('img'):
            if img.get('src'):
                src = img['src']
                if src.startswith('//'):
                    src = 'https:' + src
                    images.append(src)
                elif src.startswith(('http://', 'https://')):
                    images.append(src)
    
    # Убираем дубликаты
    seen = set()
    unique = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    
    return unique

def fetch_full_article(url):
    """Загрузка полного текста статьи"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None, []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем мусор
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        # Селекторы для текста
        content_selectors = [
            '.topic-body__content', '.b-topic__content',
            '.article__text', '.article-text',
            '.text-content', '.news-content',
            '.post-content', '.entry-content',
            'article', '[itemprop="articleBody"]'
        ]
        
        content = None
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        if not content:
            # Если не нашли, собираем параграфы
            paragraphs = soup.find_all('p')
            content_text = []
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 50:
                    content_text.append(text)
            if content_text:
                text = '\n\n'.join(content_text[:MAX_PARAGRAPHS])
                return text, []
        
        if content:
            text = content.get_text()
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r' +', ' ', text)
            text = text.strip()
            return text, []
        
        return None, []
        
    except requests.exceptions.Timeout:
        print(f"      ⏱️ Таймаут: {url[:60]}...")
        return None, []
    except Exception as e:
        return None, []

def ai_rewrite_text(text):
    """Перефразирование текста"""
    if not text or len(text) < 100:
        return text
    
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил'],
        'произошло': ['случилось', 'состоялось', 'имело место'],
        'новый': ['свежий', 'актуальный', 'последний'],
        'важный': ['значительный', 'ключевой', 'главный']
    }
    
    for word, replacements in synonyms.items():
        if word in text:
            text = text.replace(word, random.choice(replacements))
    
    return text

def fetch_and_save():
    """Основная функция сбора новостей"""
    print(f"\n{'='*60}")
    print(f"  🔴 НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    json_path = 'public/news_data.json'
    
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
            print(f"📚 Загружено {len(old_news)} существующих новостей")
        except:
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        
        for feed_url in feeds:
            print(f"  🔍 RSS: {feed_url.split('/')[2]}")
            try:
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"    ✅ {entry.title[:60]}...")
                    
                    # Получаем картинки
                    images = extract_images_from_entry(entry)
                    
                    # Загружаем текст статьи
                    full_text, _ = fetch_full_article(entry.link)
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    if description:
                        soup = BeautifulSoup(description, 'html.parser')
                        description = soup.get_text()[:200]
                    
                    # Формируем контент
                    if full_text:
                        rewritten = ai_rewrite_text(full_text)
                        paragraphs = rewritten.split('\n\n')[:MAX_PARAGRAPHS]
                        content_html = ''.join([f'<p>{p.strip()}</p>\n' for p in paragraphs if p.strip()])
                        print(f"      📝 Текст: {len(content_html)} символов")
                    else:
                        content_html = f'<p>{description}</p>\n<p>Читайте подробности на ТОЛК.</p>'
                    
                    # Создаём запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:200] + '...' if len(description) > 200 else description,
                        'content': content_html,
                        'category': category,
                        'images': images[:3],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
                    # Сохраняем в Firebase
                    try:
                        fb_data = news_item.copy()
                        fb_data['timestamp'] = firestore.SERVER_TIMESTAMP
                        db.collection('news').add(fb_data)
                    except:
                        pass
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"    ❌ Ошибка: {feed_url}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ СБОРА:")
    print(f"   📊 Всего новостей: {len(all_news)}")
    print(f"   🖼️ С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"   📝 С текстом: {sum(1 for item in all_news if len(item.get('content', '')) > 100)}")
    print(f"   ➕ Добавлено новых: {new_count}")
    print(f"{'='*60}")

if __name__ == '__main__':
    fetch_and_save()