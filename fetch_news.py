# fetch_news.py - ПОЛНАЯ ВЕРСИЯ СО ВСЕМИ КАТЕГОРИЯМИ
print("🚀 Запуск скрипта...")

import feedparser
import json
import time
from datetime import datetime
import hashlib
import random
import requests
from urllib.parse import urlparse
import re
import os

print("✅ Базовые библиотеки загружены")

# Firebase загружаем с защитой
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    print("✅ Firebase загружен")
    
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase инициализирован")
        FIREBASE_OK = True
    else:
        print("⚠️ serviceAccountKey.json не найден")
        FIREBASE_OK = False
except Exception as e:
    print(f"⚠️ Ошибка Firebase: {e}")
    FIREBASE_OK = False

# ============ НАСТРОЙКИ ============
TIMEOUT = 5  # Таймаут для запросов
MAX_ARTICLES_PER_FEED = 3  # По 3 статьи с каждой ленты
REQUEST_DELAY = 1  # Задержка между запросами

# ============ RSS ИСТОЧНИКИ - ВСЕ КАТЕГОРИИ ============
RSS_FEEDS = {
    'Политика': [
        'https://lenta.ru/rss/news/politics',
        'https://ria.ru/export/rss2/politics/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://rg.ru/xml/index.xml',
        'https://www.kommersant.ru/RSS/news.xml',
        'https://iz.ru/export/rss/politics.xml'
    ],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://www.vedomosti.ru/rss/news',
        'https://1prime.ru/feed/rss/',
        'https://www.rbc.ru/rss/',
        'https://iz.ru/export/rss/economics.xml'
    ],
    'Технологии': [
        'https://lenta.ru/rss/news/technology',
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://habr.com/ru/rss/news/?fl=ru',
        'https://3dnews.ru/news/rss/',
        'https://www.ixbt.com/export/news.xml',
        'https://www.ferra.ru/export/rss/news/'
    ],
    'Авто': [
        'https://lenta.ru/rss/news/auto',
        'https://news.rambler.ru/rss/auto/',
        'https://www.zr.ru/content/news/rss/',
        'https://motor.ru/rss',
        'https://www.autonews.ru/export/rss2/news/index.xml',
        'https://auto.mail.ru/rss/news/'
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
        'https://gameguru.ru/rss/news.xml',
        'https://stopgame.ru/rss/news.xml',
        'https://www.goha.ru/rss/news',
        'https://kanobu.ru/rss/',
        'https://cyber.sports.ru/rss/'
    ],
    'Культура': [
        'https://lenta.ru/rss/news/art',
        'https://ria.ru/export/rss2/culture/index.xml',
        'https://tvkultura.ru/rss/news.xml',
        'https://www.kommersant.ru/RSS/theme/3.xml',
        'https://www.mk.ru/rss/culture/index.xml',
        'https://iz.ru/export/rss/culture.xml'
    ],
    'Спорт': [
        'https://lenta.ru/rss/news/sport',
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://www.sport-express.ru/news/russia/rss/',
        'https://news.sportbox.ru/rss',
        'https://www.championat.com/news/rss/',
        'https://rsport.ria.ru/export/rss2/index.xml'
    ]
}

def extract_images_from_entry(entry):
    """Извлечение картинок из RSS"""
    images = []
    try:
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('url'):
                    images.append(media['url'])
        
        if hasattr(entry, 'enclosures'):
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('image'):
                    img_url = enclosure.get('href', enclosure.get('url'))
                    if img_url:
                        images.append(img_url)
        
        summary = entry.get('summary', '') or entry.get('description', '')
        if summary:
            soup = BeautifulSoup(summary, 'html.parser')
            for img in soup.find_all('img'):
                if img.get('src'):
                    src = img['src']
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/') and hasattr(entry, 'link'):
                        parsed = urlparse(entry.link)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    images.append(src)
    except:
        pass
    
    # Убираем дубликаты
    seen = set()
    unique = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    
    return unique

def fetch_article_text(url):
    """Загружает текст статьи (упрощенно)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем мусор
        for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        
        # Пробуем найти основной контент
        content = soup.find('article') or soup.find('div', class_=re.compile('article|content|text|news'))
        
        if content:
            text = content.get_text()
        else:
            text = soup.get_text()
        
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()[:1500]  # Ограничиваем длину
        
    except:
        return None

def ai_rewrite_text(text):
    """Простое перефразирование"""
    if not text:
        return text
    
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил'],
        'произошло': ['случилось', 'состоялось', 'имело место'],
        'новый': ['свежий', 'актуальный', 'последний'],
        'важный': ['значительный', 'ключевой', 'главный']
    }
    
    for word, replacements in synonyms.items():
        if word in text and random.random() > 0.5:
            text = text.replace(word, random.choice(replacements))
    
    return text

def fetch_and_save():
    """Основная функция сбора новостей"""
    print(f"\n{'='*60}")
    print(f"  🔴 НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    json_path = 'public/news_data.json'
    
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
            print(f"📚 Загружено {len(old_news)} существующих новостей")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки JSON: {e}")
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    total_checked = 0
    failed_feeds = []
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        category_new = 0
        
        for feed_url in feeds:
            try:
                domain = feed_url.split('/')[2]
                print(f"  🔍 {domain}", end='')
                
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(" ⚠️ нет записей")
                    continue
                
                entries_found = 0
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    total_checked += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    # Получаем картинки
                    images = extract_images_from_entry(entry)
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    if description:
                        soup = BeautifulSoup(description, 'html.parser')
                        description = soup.get_text()[:200]
                    
                    # Пробуем получить текст статьи
                    full_text = fetch_article_text(entry.link)
                    
                    if full_text:
                        rewritten = ai_rewrite_text(full_text)
                        content_html = f'<p>{rewritten[:500]}</p>'
                    else:
                        content_html = f'<p>{description}</p>'
                    
                    # Создаём запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:150] + '...' if len(description) > 150 else description,
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
                    category_new += 1
                    entries_found += 1
                
                print(f" ✅ {entries_found} новых")
                time.sleep(REQUEST_DELAY)
                
            except Exception as e:
                print(f" ❌ ошибка")
                failed_feeds.append(feed_url)
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    # Итоги
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ СБОРА:")
    print(f"   📊 Всего новостей: {len(all_news)}")
    print(f"   🆕 Добавлено новых: {new_count}")
    print(f"   🔍 Проверено RSS: {len([f for cat in RSS_FEEDS.values() for f in cat])}")
    print(f"   ❌ Проблемных RSS: {len(failed_feeds)}")
    if failed_feeds:
        print(f"   ⚠️ Проблемные сайты: {', '.join([f.split('/')[2] for f in failed_feeds[:3]])}")
    print(f"{'='*60}")

if __name__ == '__main__':
    fetch_and_save()