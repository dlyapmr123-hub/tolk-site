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
MAX_ARTICLES_PER_FEED = 5
REQUEST_DELAY = 3
MAX_IMAGES = 5  # Больше картинок

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': [
        'https://lenta.ru/rss/news/politics',
        'https://ria.ru/export/rss2/politics/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://rg.ru/export/rss/index.xml'
    ],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://www.rbc.ru/rss/',
        'https://www.vedomosti.ru/rss/news'
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
        'https://www.championat.com/news/rss/',
        'https://www.sport-express.ru/rss/'
    ]
}

# ============ НАСТРОЙКИ ИИ ============
USE_AI = True
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"
# ВАЖНО: ВСТАВЬТЕ ВАШ КЛЮЧ! Получите на https://openrouter.ai/keys
AI_API_KEY = "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"  # Ваш ключ

if AI_API_KEY == "sk-or-v1-..." or not AI_API_KEY:
    print("⚠️ ВНИМАНИЕ: API ключ не настроен! ИИ будет отключен")
    USE_AI = False
else:
    print(f"✅ API ключ загружен, ИИ активен")

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
    
    # СПИСОК МУСОРНЫХ ФРАЗ (ВСЁ ЧТО НУЖНО УДАЛИТЬ)
    garbage_phrases = [
        # Навигация по сайту
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
        
        # Реклама и соцсети
        r'Реклама.*?Реклама',
        r'Подпишись.*?новости',
        r'Соглашение.*?terms',
        r'ООО.*?Видео',
        r'VK.*?vkvideo\.ru',
        r'Telegram',
        r'Вконтакте',
        r'VK',
        r'YouTube',
        r'Instagram',
        r'Twitter',
        r'Facebook',
        r'12\+',
        r'18\+',
        
        # Спортивный мусор
        r'Мир Российская Премьер-лига',
        r'Фонбет Чемпионат КХЛ',
        r'Олимпиада Ставки',
        r'Футбол Бокс и ММА',
        r'Зимние виды Летние виды',
        r'Хоккей Автоспорт',
        r'ЗОЖ и фитнес',
        r'\d+\s*:\s*\d+\s*\d*-й тайм Live',
        r'\d*-й тур',
        r'Сегодня \d+:\d+',
        r'Оренбург|Зенит|Крылья Советов|Динамо Мх|Металлург Мг|Трактор|Лада|Спартак|Рубин|Краснодар|Торпедо|ХК Сочи|ЦСКА|Динамо М',
        
        # Общее
        r'Читайте также:.*?(?=\.|$)',
        r'Фото:.*?(?=\.|$)',
        r'Видео:.*?(?=\.|$)',
        r'©.*?\d{4}',
        r'Все права защищены',
        r'Источник:.*?(?=\.|$)',
        r'Ссылка:.*?(?=\.|$)',
        r'Поделиться',
        r'Скопировать ссылку',
        r'Комментарии',
        r'Обсудить',
        r'Оставить комментарий',
    ]
    
    for pattern in garbage_phrases:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Убираем множественные точки и пробелы
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_main_text(html_content, url):
    """Извлечение ПОЛНОГО текста статьи с картинками"""
    if not html_content:
        return None, []
    
    images = []
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # ========== ИЩЕМ КАРТИНКИ ==========
        # Ищем все картинки на странице
        for img in soup.find_all('img'):
            img_url = img.get('src') or img.get('data-src') or img.get('data-original')
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    # Относительный путь
                    parsed_url = urlparse(url)
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    img_url = base_url + img_url
                
                # Проверяем, что это не иконка и не логотип
                if not re.search(r'(icon|logo|avatar|favicon|pixel|spacer|button|banner|ad|reklama)', img_url.lower()):
                    if re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', img_url.lower()):
                        images.append(img_url)
        
        # ========== Удаляем мусор ==========
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
            tag.decompose()
        
        # Удаляем рекламные блоки
        for class_name in ['ad', 'ads', 'advertisement', 'banner', 'promo', 'subscribe', 'newsletter',
                          'menu', 'navigation', 'navbar', 'sidebar', 'comments', 'share', 'social',
                          'tags', 'related', 'popular', 'cookie', 'popup']:
            for element in soup.find_all(class_=re.compile(class_name, re.I)):
                element.decompose()
        
        # ========== ИЩЕМ СТАТЬЮ ==========
        article = None
        article = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'article|post|content|text|story|news-body', re.I))
        
        if not article:
            article = soup.find('body')
        
        if not article:
            return None, images
        
        # ========== СОБИРАЕМ ТЕКСТ ==========
        paragraphs = article.find_all('p')
        text_parts = []
        
        for p in paragraphs:
            p_text = p.get_text(strip=True)
            
            # Фильтруем короткие и мусорные параграфы
            if len(p_text) < 40:
                continue
            
            # Проверяем на мусор
            is_garbage = False
            garbage_check = ['реклама', 'подпишись', 'telegram', 'vk', 'вконтакте', 
                           'youtube', 'instagram', 'cookie', 'конфиденциальность']
            
            for word in garbage_check:
                if word in p_text.lower():
                    is_garbage = True
                    break
            
            if not is_garbage:
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
            
            print(f"      📸 Найдено картинок: {len(unique_images)}")
            return full_text, unique_images[:MAX_IMAGES]
        
        return None, images[:MAX_IMAGES]
        
    except Exception as e:
        print(f"      ⚠️ Ошибка парсинга: {e}")
        return None, images[:MAX_IMAGES]

def fetch_article_data(url):
    """Загружает статью и картинки"""
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
            return None, []
        
        text, images = extract_main_text(response.text, url)
        
        if text and len(text) > 200:
            print(f"    ✅ Текст: {len(text)} символов, Картинки: {len(images)}")
            return text, images
        else:
            print(f"    ⚠️ Текст слишком короткий")
            return None, images
        
    except Exception as e:
        print(f"    ❌ Ошибка загрузки: {e}")
        return None, []

def ai_rewrite_text(text, title, category):
    """Перефразирование текста через ИИ"""
    if not text or len(text) < 200 or not USE_AI:
        return text
    
    try:
        print(f"    🤖 ИИ обрабатывает текст...")
        
        prompt = f"""Перепиши эту новость своими словами, сохранив все важные факты и детали.
Напиши полноценную статью из 3-5 абзацев.
Убери любую рекламу, ссылки на другие сайты, призывы подписаться.
Сохрани только суть новости, переформулируй её уникально.

Категория: {category}
Заголовок: {title}

Текст новости:
{text}

Твоя переписанная статья (только текст, без пояснений):"""

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tolk-1.web.app",
            "X-Title": "Tolk News"
        }
        
        data = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 800
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"]
            rewritten = clean_text(rewritten)
            
            if len(rewritten) > 200:
                print(f"    ✅ ИИ обработал, {len(rewritten)} символов")
                return rewritten
        
        return text
        
    except Exception as e:
        print(f"    ⚠️ Ошибка ИИ: {e}")
        return text

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
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
                    continue
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 {entry.title[:80]}...")
                    
                    # Загружаем текст и картинки
                    full_text, images = fetch_article_data(entry.link)
                    
                    if not full_text:
                        continue
                    
                    # Получаем описание
                    description = entry.get('summary', '') or entry.get('description', '')
                    description = re.sub(r'<[^>]+>', '', description)
                    description = clean_text(description)[:200]
                    
                    # Применяем ИИ
                    if USE_AI:
                        full_text = ai_rewrite_text(full_text, entry.title, category)
                    
                    # Форматируем в HTML
                    paragraphs = full_text.split('. ')
                    content_html = ''
                    for i, sent in enumerate(paragraphs[:7]):  # Больше абзацев
                        if sent.strip():
                            content_html += f'<p>{sent.strip()}.</p>\n'
                    
                    # Создаем запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:150] + '...' if len(description) > 150 else description,
                        'content': content_html,
                        'category': category,
                        'images': images,  # Картинки из статьи
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
    
    # Сохраняем версию
    version_data = {
        'version': datetime.now().timestamp(),
        'updated': datetime.now().isoformat(),
        'total': len(all_news),
        'new': new_count,
        'processed': total_processed
    }
    
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}")

if __name__ == '__main__':
    try:
        fetch_and_save()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        traceback.print_exc()