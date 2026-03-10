#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ФИНАЛЬНАЯ ВЕРСИЯ - УЛУЧШЕННЫЙ ПАРСИНГ КАРТИНОК
Специальная обработка для Habr, Lenta, РИА
Московское время для публикаций
"""

import feedparser
import json
import hashlib
import re
import time
import html
import os
import sys
import traceback
import uuid
import warnings
import urllib3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup

# Отключаем предупреждения о SSL
warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Конфигурация с GigaChat
CONFIG = {
    'TIMEOUT': 15,
    'MAX_ARTICLES_PER_FEED': 30,
    'REQUEST_DELAY': 1,
    'MAX_IMAGES': 3,
    'MIN_TEXT_LENGTH': 100,
    'MAX_NEWS_TOTAL': 500,
    'USE_AI': True,
    
    # GigaChat API
    'AI_MODEL': 'GigaChat',
    'AI_API_URL': 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions',
    'AI_AUTH_URL': 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
    'AI_CLIENT_SECRET': os.environ.get('GIGACHAT_CLIENT_SECRET', ''),
    
    # Отключаем проверку SSL для работы в России
    'AI_VERIFY_SSL': False,
    
    'SITE_URL': 'https://tolk-1.web.app'
}

# RSS источники
RSS_FEEDS = {
    'Политика': [           
    'https://iz.ru/export/rss.xml',                         # Известия (работает)
    'https://www.kommersant.ru/RSS/news.xml',               # Коммерсантъ (работает)
],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
    ],
    'Технологии': [
        'https://lenta.ru/rss/news/technology',
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://habr.com/ru/rss/news/?fl=ru',
    ],
    # Замените в RSS_FEEDS проблемные категории на эти
'Авто': [
    'https://lenta.ru/rss/news/auto',
    'https://ria.ru/export/rss2/auto/index.xml',
    'https://motor.ru/rss',
    'https://news.rambler.ru/rss/auto/',  # Добавить
    'https://auto.mail.ru/rss/',          # Добавить
],
'Киберспорт': [
    'https://www.cybersport.ru/rss',
    'https://stopgame.ru/rss/news.xml',  
    'https://kanobu.ru/rss/',                 
],
'Культура': [
    'https://lenta.ru/rss/news/art',
    'https://ria.ru/export/rss2/culture/index.xml',
    'https://www.mk.ru/rss/culture/index.xml',  # Добавить
    'https://rg.ru/export/rss/kultura/index.xml', # Добавить
],
    'Спорт': [
        'https://lenta.ru/rss/news/sport',
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://www.championat.com/news/rss/',
    ]
}

class NewsCollector:
    """Сборщик новостей с улучшенным парсингом картинок"""
    
    def __init__(self):
        self.existing_links = set()
        self.all_news = []
        self.new_count = 0
        self.total_processed = 0
        self.access_token = None
        self.token_expires = 0
        
        self.stats = {
            'page_loaded': 0,
            'text_found': 0,
            'already_exists': 0,
            'with_images': 0,
            'errors': 0,
            'ai_processed': 0
        }
        
        self.seen_images = set()
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji = {
            "INFO": "📌", "SUCCESS": "✅", "WARNING": "⚠️",
            "ERROR": "❌", "LOAD": "📥", "AI": "🤖",
            "IMAGE": "📸", "TEXT": "📝"
        }.get(level, "📌")
        print(f"{emoji} [{timestamp}] {message}")
    
    def get_moscow_time(self) -> str:
        """Возвращает текущее московское время в формате ЧЧ:ММ, ДД.ММ.ГГГГ"""
        try:
            # Получаем текущее время в UTC и добавляем 3 часа для Москвы
            now_utc = datetime.utcnow()
            moscow_time = now_utc + timedelta(hours=3)
            return moscow_time.strftime('%H:%M, %d.%m.%Y')
        except Exception as e:
            # Если что-то пошло не так, возвращаем локальное время
            self.log(f"Ошибка получения московского времени: {e}", "WARNING")
            return datetime.now().strftime('%H:%M, %d.%m.%Y')
    
    def get_gigachat_token(self) -> Optional[str]:
        """Получение токена доступа к GigaChat"""
        try:
            if self.access_token and time.time() < self.token_expires:
                return self.access_token
            
            self.log("Получение токена GigaChat...", "AI")
            
            headers = {
                'Authorization': f'Basic {CONFIG["AI_CLIENT_SECRET"]}',
                'RqUID': str(uuid.uuid4()),
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {'scope': 'GIGACHAT_API_PERS'}
            
            response = requests.post(
                CONFIG['AI_AUTH_URL'],
                headers=headers,
                data=data,
                timeout=10,
                verify=CONFIG['AI_VERIFY_SSL']
            )
            
            if response.status_code == 200:
                result = response.json()
                self.access_token = result['access_token']
                
                if 'expires_in' in result:
                    self.token_expires = time.time() + result['expires_in'] - 60
                else:
                    self.token_expires = time.time() + 1800 - 60
                    self.log("⚠️ expires_in не найден, использую 30 мин", "WARNING")
                
                self.log("✅ Токен получен", "AI")
                return self.access_token
            else:
                self.log(f"❌ Ошибка получения токена: {response.status_code}", "ERROR")
                return None
                
        except Exception as e:
            self.log(f"❌ Ошибка при получении токена: {e}", "ERROR")
            return None
    
    def extract_habr_images(self, soup, url) -> List[str]:
        """Специальный парсер картинок для Хабра"""
        habr_images = []
        
        # 1. Пробуем meta og:image (самый надежный способ)
        meta_image = soup.find('meta', property='og:image')
        if meta_image and meta_image.get('content'):
            img_url = meta_image['content']
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            habr_images.append(img_url)
            self.log(f"Найдено og:image для Habr", "IMAGE")
            return habr_images[:CONFIG['MAX_IMAGES']]
        
        # 2. Ищем в статье
        article = soup.find('article')
        if article:
            for img in article.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src:
                    continue
                
                img_class = ' '.join(img.get('class', []))
                if re.search(r'avatar|user-picture|userpic|author', img_class, re.I):
                    continue
                
                if re.search(r'avatar|icon|logo|favicon|pixel|spacer', src.lower()):
                    continue
                
                if src.startswith('//'):
                    src = 'https:' + src
                habr_images.append(src)
                
                if len(habr_images) >= CONFIG['MAX_IMAGES']:
                    break
        
        return habr_images[:CONFIG['MAX_IMAGES']]
    
    def extract_lenta_images(self, soup) -> List[str]:
        """Специальный парсер картинок для Ленты"""
        images = []
        
        lenta_images = soup.find_all('img', class_='picture__image')
        for img in lenta_images:
            src = img.get('src')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                images.append(src)
                self.log("Найдена картинка Lenta (picture__image)", "IMAGE")
        
        if not images:
            article = soup.find('article')
            if article:
                for img in article.find_all('img'):
                    src = img.get('src') or img.get('data-src')
                    if src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                        if src.startswith('//'):
                            src = 'https:' + src
                        images.append(src)
        
        return images[:CONFIG['MAX_IMAGES']]
    
    def extract_ria_images(self, soup) -> List[str]:
        """Специальный парсер картинок для РИА"""
        images = []
        
        ria_images = soup.find_all('img', class_=re.compile(r'photoview|media', re.I))
        for img in ria_images:
            src = img.get('src')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                images.append(src)
        
        if not images:
            article = soup.find('article')
            if article:
                for img in article.find_all('img'):
                    src = img.get('src') or img.get('data-src')
                    if src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                        if src.startswith('//'):
                            src = 'https:' + src
                        images.append(src)
        
        return images[:CONFIG['MAX_IMAGES']]
    
    def extract_cybersport_images(self, soup) -> List[str]:
        """Специальный парсер картинок для Cybersport"""
        images = []
        
        article = soup.find('article')
        if article:
            for img in article.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                    if src.startswith('//'):
                        src = 'https:' + src
                    images.append(src)
        
        return images[:CONFIG['MAX_IMAGES']]
    
    def extract_text_from_page(self, url: str) -> Tuple[Optional[str], List[str]]:
        """Загрузка страницы и извлечение текста"""
        try:
            self.log(f"Загрузка: {url[:60]}...", "LOAD")
            
            response = self.session.get(url, timeout=CONFIG['TIMEOUT'])
            
            if response.status_code != 200:
                return None, []
            
            if len(response.text) < 1000:
                return None, []
            
            self.stats['page_loaded'] += 1
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            images = []
            
            if 'habr.com' in url.lower():
                images = self.extract_habr_images(soup, url)
            elif 'lenta.ru' in url.lower():
                images = self.extract_lenta_images(soup)
            elif 'ria.ru' in url.lower():
                images = self.extract_ria_images(soup)
            elif 'cybersport.ru' in url.lower():
                images = self.extract_cybersport_images(soup)
            else:
                meta_image = soup.find('meta', property='og:image')
                if meta_image and meta_image.get('content'):
                    img_url = meta_image['content']
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    images.append(img_url)
                else:
                    article = soup.find('article')
                    if article:
                        for img in article.find_all('img'):
                            src = img.get('src') or img.get('data-src')
                            if src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                                img_class = ' '.join(img.get('class', []))
                                if not re.search(r'avatar|user|author|profile', img_class, re.I):
                                    if src.startswith('//'):
                                        src = 'https:' + src
                                    images.append(src)
            
            unique_images = []
            seen = set()
            for img in images:
                if img not in seen:
                    seen.add(img)
                    unique_images.append(img)
            
            if unique_images:
                self.stats['with_images'] += len(unique_images)
                self.log(f"Найдено картинок: {len(unique_images)}", "IMAGE")
            
            text_parts = []
            
            article = soup.find('article')
            if article:
                paragraphs = article.find_all('p')
                for p in paragraphs[:15]:
                    text = p.get_text(strip=True)
                    if len(text) > 40:
                        text_parts.append(text)
            
            if not text_parts:
                paragraphs = soup.find_all('p')
                for p in paragraphs[:20]:
                    text = p.get_text(strip=True)
                    if len(text) > 50:
                        text_parts.append(text)
            
            if text_parts:
                full_text = ' '.join(text_parts)
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                
                self.log(f"Текст: {len(full_text)} символов", "TEXT")
                self.stats['text_found'] += 1
                
                return full_text, unique_images[:CONFIG['MAX_IMAGES']]
            
            return None, []
            
        except Exception as e:
            self.stats['errors'] += 1
            return None, []
    
    def ai_rewrite(self, text: str, title: str, category: str) -> str:
        """GigaChat переписывание с повторными попытками"""
        if not CONFIG['USE_AI'] or len(text) < 100:
            return text
        
        short_text = text[:800] if len(text) > 800 else text
        
        for attempt in range(3):
            try:
                token = self.get_gigachat_token()
                if not token:
                    return text
                
                self.log(f"GigaChat обрабатывает (попытка {attempt+1}/3)...", "AI")
                
                prompt = f"""Кратко перескажи новость (3-4 предложения):

Заголовок: {title}
Текст: {short_text}

Пересказ:"""
                
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": CONFIG['AI_MODEL'],
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 300
                }
                
                response = requests.post(
                    CONFIG['AI_API_URL'],
                    headers=headers,
                    json=data,
                    timeout=15,
                    verify=CONFIG['AI_VERIFY_SSL']
                )
                
                if response.status_code == 200:
                    result = response.json()
                    rewritten = result["choices"][0]["message"]["content"]
                    rewritten = re.sub(r'\s+', ' ', rewritten).strip()
                    self.stats['ai_processed'] += 1
                    self.log(f"✅ GigaChat готов: {len(rewritten)} символов", "AI")
                    return rewritten
                else:
                    self.log(f"⚠️ Ошибка GigaChat: {response.status_code}, попытка {attempt+1}", "WARNING")
                    time.sleep(2)
                    
            except Exception as e:
                self.log(f"⚠️ Ошибка в попытке {attempt+1}: {e}", "WARNING")
                time.sleep(2)
        
        self.log("❌ Все попытки GigaChat провалились, использую оригинал", "WARNING")
        return text
    
    def run(self):
        """Основной метод запуска"""
        print("\n" + "="*70)
        print("🚀 СБОРЩИК НОВОСТЕЙ (GigaChat)")
        print("📸 Улучшенный парсинг картинок")
        print("🕐 Московское время для публикаций")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")
        
        os.makedirs('public', exist_ok=True)
        json_path = 'public/news_data_v3.json'
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.all_news = json.load(f)
                    for item in self.all_news:
                        if item.get('originalLink'):
                            self.existing_links.add(item['originalLink'])
                self.log(f"Загружено {len(self.all_news)} старых новостей")
            except:
                self.all_news = []
        
        for category, feeds in RSS_FEEDS.items():
            print(f"\n📊 {category}")
            
            for feed_url in feeds:
                try:
                    feed = feedparser.parse(feed_url)
                    
                    if not feed.entries:
                        continue
                    
                    print(f"  📡 {feed_url.split('/')[-1]}: {len(feed.entries)} записей")
                    
                    for idx, entry in enumerate(feed.entries[:CONFIG['MAX_ARTICLES_PER_FEED']], 1):
                        self.total_processed += 1
                        
                        if entry.link in self.existing_links:
                            continue
                        
                        print(f"\n  [{idx}] {entry.title[:60]}...")
                        
                        full_text, images = self.extract_text_from_page(entry.link)
                        
                        if not full_text:
                            print(f"    ⚠️ Нет текста")
                            continue
                        
                        if CONFIG['USE_AI'] and len(full_text) > 100:
                            full_text = self.ai_rewrite(full_text, entry.title, category)
                        
                        sentences = re.split(r'(?<=[.!?])\s+', full_text)
                        content_html = ''
                        for s in sentences[:6]:
                            s = s.strip()
                            if s:
                                if not s.endswith(('.', '!', '?')):
                                    s += '.'
                                content_html += f'<p>{s}</p>\n'
                        
                        if not content_html:
                            content_html = f'<p>{full_text[:300]}</p>'
                        
                        news_item = {
                            'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                            'title': entry.title.strip()[:250],
                            'description': full_text[:200] + '...' if len(full_text) > 200 else full_text,
                            'content': content_html,
                            'category': category,
                            'images': images,
                            'originalLink': entry.link,
                            'published': self.get_moscow_time(),  # Московское время
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        self.all_news.append(news_item)
                        self.existing_links.add(entry.link)
                        self.new_count += 1
                        
                        print(f"    ✅ СОХРАНЕНО | Текст: {len(full_text)}")
                        
                        time.sleep(CONFIG['REQUEST_DELAY'])
                        
                except Exception as e:
                    print(f"  ❌ Ошибка: {e}")
                    self.stats['errors'] += 1
                    continue
        
        self.all_news.sort(key=lambda x: x['timestamp'], reverse=True)
        
        if len(self.all_news) > CONFIG['MAX_NEWS_TOTAL']:
            self.all_news = self.all_news[:CONFIG['MAX_NEWS_TOTAL']]
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_news, f, ensure_ascii=False, indent=2)
        
        version_data = {
            'version': datetime.now().timestamp(),
            'updated': datetime.now().isoformat(),
            'total': len(self.all_news),
            'new': self.new_count,
            'processed': self.total_processed,
            'ai_processed': self.stats['ai_processed'],
            'with_images': self.stats['with_images']
        }
        
        with open('public/version.json', 'w', encoding='utf-8') as f:
            json.dump(version_data, f, ensure_ascii=False, indent=2)
        
        print("\n" + "="*70)
        print("📊 ИТОГИ:")
        print(f"   Всего новостей: {len(self.all_news)}")
        print(f"   Новых добавлено: {self.new_count}")
        print(f"   Всего обработано: {self.total_processed}")
        print(f"   Обработано GigaChat: {self.stats['ai_processed']}")
        print(f"   С картинками: {self.stats['with_images']}")
        print(f"   Ошибок: {self.stats['errors']}")
        print("="*70)

if __name__ == '__main__':
    try:
        collector = NewsCollector()
        collector.run()
    except KeyboardInterrupt:
        print("\n👋 Остановлено")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        traceback.print_exc()