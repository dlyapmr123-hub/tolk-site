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

# Инициализация Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

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
        'https://stopgame.ru/rss/news.xml',
        'https://gameguru.ru/rss/news.xml'
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

# ============ ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ КАРТИНОК ============
def extract_images_from_entry(entry):
    """Извлекает ВСЕ реальные картинки из RSS записи"""
    images = []
    
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                img_url = media['url']
                if img_url.startswith(('http://', 'https://')):
                    images.append(img_url)
                    print(f"      📸 RSS media: {img_url[:60]}...")
    
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if enclosure.get('type', '').startswith('image'):
                img_url = enclosure.get('href', enclosure.get('url'))
                if img_url and img_url.startswith(('http://', 'https://')):
                    images.append(img_url)
                    print(f"      📸 RSS enclosure: {img_url[:60]}...")
    
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        soup = BeautifulSoup(summary, 'html.parser')
        for img in soup.find_all('img'):
            if img.get('src'):
                src = img['src']
                if src.startswith('//'):
                    src = 'https:' + src
                    images.append(src)
                    print(f"      📸 RSS summary: {src[:60]}...")
                elif src.startswith(('http://', 'https://')):
                    images.append(src)
                    print(f"      📸 RSS summary: {src[:60]}...")
    
    seen = set()
    unique = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    
    return unique

# ============ ФУНКЦИЯ ДЛЯ ЗАГРУЗКИ ПОЛНОЙ СТАТЬИ ============
def fetch_full_article(url):
    """Загружает полный текст статьи и дополнительные картинки"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None, []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
            element.decompose()
        
        article_images = []
        for img in soup.find_all('img'):
            if img.get('src'):
                src = img['src']
                if 'avatar' in src or 'icon' in src or 'logo' in src:
                    continue
                
                if src.startswith('//'):
                    src = 'https:' + src
                    article_images.append(src)
                elif src.startswith(('http://', 'https://')):
                    article_images.append(src)
                elif src.startswith('/'):
                    parsed = urlparse(url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    article_images.append(src)
        
        content_selectors = [
            '.topic-body__content', '.b-topic__content',
            '.article__text', '.article-text',
            '.text-content', '.news-content',
            '.post-content', '.entry-content',
            'article', '[itemprop="articleBody"]',
            '.material-content', '.news-body'
        ]
        
        content = None
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        if not content:
            paragraphs = soup.find_all('p')
            if len(paragraphs) > 3:
                content_text = []
                for p in paragraphs:
                    text = p.get_text().strip()
                    if len(text) > 50:
                        content_text.append(text)
                if content_text:
                    text = '\n\n'.join(content_text)
                    text = re.sub(r'\n\s*\n', '\n\n', text)
                    text = re.sub(r' +', ' ', text)
                    return text, article_images[:5]
        
        if content:
            text = content.get_text()
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r' +', ' ', text)
            text = text.strip()
            return text, article_images[:5]
        
        return None, article_images[:5]
        
    except Exception as e:
        print(f"      ⚠️ Ошибка: {e}")
        return None, []

# ============ ФУНКЦИЯ ПЕРЕФРАЗИРОВАНИЯ ============
def ai_rewrite_text(text):
    if not text or len(text) < 100:
        return text
    
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил'],
        'произошло': ['случилось', 'состоялось', 'имело место'],
        'новый': ['свежий', 'актуальный', 'последний'],
        'важный': ['значительный', 'ключевой', 'главный'],
        'россия': ['РФ', 'Российская Федерация', 'наша страна']
    }
    
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
    
    return ' '.join(new_words)

# ============ ОСНОВНАЯ ФУНКЦИЯ ============
def fetch_and_save():
    print(f"\n[{datetime.now()}] 🔴 НАЧАЛО СБОРА НОВОСТЕЙ")
    
    json_path = 'public/news_data_v2.json'
    
    existing_links = set()
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
    else:
        old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        
        for feed_url in feeds:
            print(f"  🔍 RSS: {feed_url}")
            try:
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"    ⚠️ Нет записей")
                    continue
                
                for entry in feed.entries[:5]:
                    if entry.link in existing_links:
                        print(f"    ⏭️ Уже есть: {entry.title[:40]}...")
                        continue
                    
                    print(f"    ✅ НОВАЯ: {entry.title[:60]}...")
                    
                    rss_images = extract_images_from_entry(entry)
                    full_text, article_images = fetch_full_article(entry.link)
                    
                    all_images = []
                    if rss_images:
                        all_images.extend(rss_images)
                    if article_images:
                        all_images.extend(article_images)
                    
                    unique_images = []
                    seen = set()
                    for img in all_images:
                        if img not in seen:
                            seen.add(img)
                            unique_images.append(img)
                    
                    print(f"      🖼️ ВСЕГО КАРТИНОК: {len(unique_images)}")
                    
                    description = entry.get('summary', '') or entry.get('description', '')
                    if description:
                        soup = BeautifulSoup(description, 'html.parser')
                        description = soup.get_text()[:200]
                    
                    if full_text:
                        rewritten = ai_rewrite_text(full_text)
                        paragraphs = rewritten.split('\n\n')[:8]
                        content_html = ''
                        for p in paragraphs:
                            if p.strip():
                                content_html += f'<p>{p.strip()}</p>\n'
                        print(f"      📝 Текст сохранён: {len(content_html)} символов")
                    else:
                        content_html = f'<p>{description}</p>\n<p>Читайте подробности на ТОЛК.</p>'
                        print(f"      ⚠️ Текст не найден, использую описание")
                    
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:200] + '...' if len(description) > 200 else description,
                        'content': content_html,
                        'category': category,
                        'images': unique_images[:5],
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
                    try:
                        fb_data = news_item.copy()
                        fb_data['timestamp'] = firestore.SERVER_TIMESTAMP
                        db.collection('news').add(fb_data)
                    except:
                        pass
                    
                    time.sleep(2)
                    
            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
                continue
    
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    news_with_images = sum(1 for item in all_news if item.get('images'))
    news_with_text = sum(1 for item in all_news if len(item.get('content', '')) > 100)
    
    print(f"\n{'='*50}")
    print(f"✅ ИТОГИ:")
    print(f"📊 Всего новостей: {len(all_news)}")
    print(f"🖼️ С картинками: {news_with_images}")
    print(f"📝 С текстом: {news_with_text}")
    print(f"➕ Добавлено новых: {new_count}")
    print(f"{'='*50}")

if __name__ == '__main__':
    fetch_and_save()