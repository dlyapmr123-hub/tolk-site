# firebase-importer.py
import feedparser
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import hashlib
import random
import firebase_admin
from firebase_admin import credentials, firestore
import schedule
import requests
from urllib.parse import urlparse, urljoin
import re
import os
import signal
import sys

# ============ НАСТРОЙКИ ============
SITE_NAME = "ТОЛК"
SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"
CHECK_INTERVAL = 5  # Проверка новых новостей каждые 5 минут

# Инициализация Firebase
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase подключен")
except Exception as e:
    print(f"❌ Ошибка подключения к Firebase: {e}")
    print("Убедитесь, что файл serviceAccountKey.json существует и корректен")
    sys.exit(1)

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

# ============ КЭШ ЗАГРУЖЕННЫХ ССЫЛОК ============
loaded_links = set()

def load_existing_links():
    """Загружает существующие ссылки из Firebase"""
    try:
        news_ref = db.collection('news')
        news = news_ref.get()
        
        for doc in news:
            data = doc.to_dict()
            if data.get('originalLink'):
                loaded_links.add(data['originalLink'])
        
        print(f"📚 Загружено {len(loaded_links)} существующих новостей")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки существующих ссылок: {e}")

def extract_images_from_entry(entry):
    """Извлекает все возможные картинки из RSS записи"""
    images = []
    
    # Проверяем media_content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    
    # Проверяем enclosures
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if enclosure.get('type', '').startswith('image'):
                images.append(enclosure.get('href', enclosure.get('url')))
    
    # Ищем в summary
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        soup = BeautifulSoup(summary, 'html.parser')
        for img in soup.find_all('img'):
            if img.get('src'):
                src = img['src']
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    if hasattr(entry, 'link'):
                        parsed = urlparse(entry.link)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                images.append(src)
    
    return list(dict.fromkeys([img for img in images if img and img.startswith('http')]))

def fetch_full_article(url):
    """Загружает полный текст статьи с сайта"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None, None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем ненужные элементы
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        # Селекторы для разных сайтов
        content_selectors = [
            '.topic-body__content', '.article-text', '.b-topic__content',  # Lenta
            '.article__text', '.article-text',  # RIA
            '.article__text', '.article-text',  # RBC
            '.news-content', '.text-content',  # TASS
            '.article__text', '.post__text',  # Habr
            '.news-item__content', '.article-content',  # Championat
            'article', '[itemprop="articleBody"]', '.post-content',
            '.entry-content', '.content', '.material-content', '.news-body'
        ]
        
        content = None
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        if content:
            # Очищаем текст
            for tag in content.find_all(['div', 'span', 'br']):
                tag.append('\n')
            
            text = content.get_text()
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r' +', ' ', text)
            text = text.strip()
            
            # Ищем дополнительные картинки в статье
            article_images = []
            for img in content.find_all('img'):
                if img.get('src'):
                    src = img['src']
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        parsed = urlparse(url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    article_images.append(src)
            
            return text, article_images
        
        return None, None
        
    except Exception as e:
        print(f"    ⚠️ Ошибка загрузки статьи: {e}")
        return None, None

def ai_rewrite_text(text):
    """Переписывает текст, делая его уникальным"""
    if not text or len(text) < 100:
        return text
    
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил', 'прокомментировал'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил', 'огласил', 'доложил'],
        'произошло': ['случилось', 'состоялось', 'имело место', 'произошло событие'],
        'начался': ['стартовал', 'открылся', 'запустился', 'взял старт'],
        'закончился': ['завершился', 'финишировал', 'подошел к концу', 'окончился'],
        'новый': ['свежий', 'актуальный', 'последний', 'современный'],
        'важный': ['значительный', 'ключевой', 'главный', 'существенный'],
        'россия': ['РФ', 'Российская Федерация', 'наша страна'],
        'российский': ['отечественный', 'национальный']
    }
    
    # Замена слов
    words = text.split()
    new_words = []
    
    for word in words:
        word_lower = word.lower().strip('.,!?()"«»')
        if word_lower in synonyms and random.random() > 0.5:
            replacement = random.choice(synonyms[word_lower])
            if word[0].isupper():
                replacement = replacement.capitalize()
            new_words.append(replacement)
        else:
            new_words.append(word)
    
    new_text = ' '.join(new_words)
    
    # Добавляем вводные конструкции
    intros = [
        'По информации источников, ',
        'Как стало известно, ',
        'Согласно полученным данным, '
    ]
    
    sentences = re.split(r'(?<=[.!?])\s+', new_text)
    result = []
    
    for i, sentence in enumerate(sentences):
        if i == 0 and random.random() > 0.6:
            intro = random.choice(intros)
            result.append(intro + sentence[0].lower() + sentence[1:])
        else:
            result.append(sentence)
    
    return ' '.join(result)

def fetch_and_save_news():
    """Собирает новые новости и сохраняет в Firebase"""
    print(f"\n[{datetime.now()}] 🔄 НАЧАЛО ПРОВЕРКИ НОВЫХ НОВОСТЕЙ...")
    
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        
        for url in feeds:
            try:
                print(f"  🔍 RSS: {url}")
                feed = feedparser.parse(url)
                
                if not feed.entries:
                    print(f"    ⚠️ Нет записей")
                    continue
                
                for entry_idx, entry in enumerate(feed.entries[:5]):
                    # Проверяем по ссылке, а не по заголовку
                    if entry.link in loaded_links:
                        print(f"    ⏭️ Уже есть: {entry.title[:40]}...")
                        continue
                    
                    print(f"    ✅ НОВАЯ: {entry.title[:60]}...")
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    if description:
                        soup = BeautifulSoup(description, 'html.parser')
                        description = soup.get_text()[:200]
                    
                    # Извлекаем картинки
                    images = extract_images_from_entry(entry)
                    
                    # Загружаем полный текст
                    full_text, article_images = fetch_full_article(entry.link)
                    
                    # Добавляем картинки из статьи
                    if article_images:
                        images.extend(article_images)
                    
                    # Если нет картинок, используем заглушку
                    if not images:
                        images = [f'https://loremflickr.com/600/400/{category.lower()}']
                    
                    # Формируем текст статьи
                    if full_text:
                        rewritten_text = ai_rewrite_text(full_text)
                        paragraphs = rewritten_text.split('\n\n')
                        content_html = ''
                        for p in paragraphs[:10]:  # Ограничиваем до 10 параграфов
                            if p.strip():
                                content_html += f'<p>{p.strip()}</p>\n'
                    else:
                        content_html = f'<p>{description}</p>\n<p>Читайте подробности на ТОЛК.</p>'
                    
                    # Сохраняем в Firebase
                    news_data = {
                        'title': entry.title[:200],
                        'description': description[:200] + '...' if len(description) > 200 else description,
                        'content': content_html,
                        'category': category,
                        'images': images[:5],
                        'source': url,
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': firestore.SERVER_TIMESTAMP
                    }
                    
                    doc_ref = db.collection('news').document()
                    doc_ref.set(news_data)
                    
                    # Добавляем ссылку в кэш
                    loaded_links.add(entry.link)
                    new_count += 1
                    
                    print(f"      🖼️ Картинок: {len(images)}")
                    print(f"      📝 Текст: {len(content_html)} символов")
                    
                    time.sleep(2)  # Задержка между запросами
                    
            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
                continue
    
    print(f"\n[{datetime.now()}] ✅ Добавлено новых новостей: {new_count}")

def cleanup_old_news():
    """Удаляет старые новости (оставляет только последние 500)"""
    try:
        print(f"\n[{datetime.now()}] 🧹 ОЧИСТКА СТАРЫХ НОВОСТЕЙ...")
        
        news_ref = db.collection('news').order_by('timestamp', direction=firestore.Query.DESCENDING)
        news = news_ref.get()
        
        if len(news) > 500:
            for doc in news[500:]:
                doc.reference.delete()
                print(f"  🗑️ Удалена: {doc.id}")
        
        print(f"[{datetime.now()}] ✅ Очистка завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")

def signal_handler(sig, frame):
    print(f"\n[{datetime.now()}] 👋 Остановка импортера...")
    sys.exit(0)

# ============ ЗАПУСК ============
if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    print("=" * 60)
    print("🚀 ИМПОРТЕР НОВОСТЕЙ ТОЛК")
    print("=" * 60)
    print(f"✅ Firebase подключен")
    print(f"📅 Проверка новых новостей каждые {CHECK_INTERVAL} минут")
    print("=" * 60)
    
    # Загружаем существующие ссылки
    load_existing_links()
    
    # Первый запуск
    fetch_and_save_news()
    
    # Запускаем расписание
    schedule.every(CHECK_INTERVAL).minutes.do(fetch_and_save_news)
    schedule.every(6).hours.do(cleanup_old_news)
    
    print(f"\n[{datetime.now()}] 🔄 ИМПОРТЕР ЗАПУЩЕН В ФОНОВОМ РЕЖИМЕ")
    print("Нажмите Ctrl+C для остановки\n")
    
    while True:
        schedule.run_pending()
        time.sleep(10)