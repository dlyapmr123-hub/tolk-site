#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ФИНАЛЬНАЯ ВЕРСИЯ - ЗАГРУЖАЕТ СТРАНИЦЫ И БЕРЕТ ТЕКСТ
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
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup

# Конфигурация
CONFIG = {
    'TIMEOUT': 15,
    'MAX_ARTICLES_PER_FEED': 20,  # Уменьшим для скорости
    'REQUEST_DELAY': 1,
    'MAX_IMAGES': 3,
    'MIN_TEXT_LENGTH': 200,
    'MAX_NEWS_TOTAL': 500,
    'USE_AI': True,
    'AI_MODEL': 'gpt-3.5-turbo',
    'AI_API_URL': 'https://openrouter.ai/api/v1/chat/completions',
    'AI_API_KEY': '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',
    'SITE_URL': 'https://tolk-1.web.app'
}

# БЫСТРЫЕ ИСТОЧНИКИ
RSS_FEEDS = {
    'Политика': [
        'https://lenta.ru/rss/news/politics',
        'https://ria.ru/export/rss2/politics/index.xml',
    ],
    'Экономика': [
        'https://lenta.ru/rss/news/economics',
        'https://ria.ru/export/rss2/economy/index.xml',
    ],
    'Технологии': [
        'https://lenta.ru/rss/news/technology',
        'https://ria.ru/export/rss2/technology/index.xml',
    ],
    'Авто': [
        'https://lenta.ru/rss/news/auto',
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
    ],
    'Культура': [
        'https://lenta.ru/rss/news/art',
        'https://ria.ru/export/rss2/culture/index.xml',
    ],
    'Спорт': [
        'https://lenta.ru/rss/news/sport',
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://www.championat.com/news/rss/',
    ]
}

class NewsCollector:
    """Сборщик новостей с загрузкой страниц"""
    
    def __init__(self):
        self.existing_links = set()
        self.all_news = []
        self.new_count = 0
        self.total_processed = 0
        self.stats = {
            'page_loaded': 0,
            'text_found': 0,
            'already_exists': 0,
            'with_images': 0,
            'errors': 0
        }
        
        # Настройка сессии для запросов
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        })
    
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji = {
            "INFO": "📌", "SUCCESS": "✅", "WARNING": "⚠️", 
            "ERROR": "❌", "LOAD": "📥", "PARSE": "🔍", 
            "AI": "🤖", "IMAGE": "📸", "TEXT": "📝"
        }.get(level, "📌")
        print(f"{emoji} [{timestamp}] {message}")
    
    def extract_text_from_page(self, url: str) -> Tuple[Optional[str], List[str]]:
        """ЗАГРУЗКА СТРАНИЦЫ И ИЗВЛЕЧЕНИЕ ТЕКСТА"""
        try:
            self.log(f"Загрузка страницы: {url[:60]}...", "LOAD")
            
            response = self.session.get(url, timeout=CONFIG['TIMEOUT'])
            if response.status_code != 200:
                self.log(f"Ошибка HTTP: {response.status_code}", "ERROR")
                return None, []
            
            self.stats['page_loaded'] += 1
            
            # Парсим страницу
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Удаляем мусор
            for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            # Ищем КАРТИНКИ
            images = []
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        src = f"{parsed.scheme}://{parsed.netloc}{src}"
                    
                    if re.search(r'\.(jpg|jpeg|png|webp|gif)', src.lower()):
                        if not re.search(r'(logo|icon|avatar|favicon|pixel|spacer)', src.lower()):
                            images.append(src)
            
            # Ищем ТЕКСТ
            text_parts = []
            
            # 1. Ищем article
            article = soup.find('article')
            if article:
                paragraphs = article.find_all('p')
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if len(text) > 30:
                        text_parts.append(text)
            
            # 2. Ищем main
            if not text_parts:
                main = soup.find('main')
                if main:
                    paragraphs = main.find_all('p')
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 30:
                            text_parts.append(text)
            
            # 3. Ищем div с контентом
            if not text_parts:
                for class_name in ['article', 'content', 'text', 'post', 'news', 'material']:
                    content = soup.find('div', class_=re.compile(class_name, re.I))
                    if content:
                        paragraphs = content.find_all('p')
                        for p in paragraphs:
                            text = p.get_text(strip=True)
                            if len(text) > 30:
                                text_parts.append(p.get_text(strip=True))
                        if text_parts:
                            break
            
            # 4. Берем все параграфы body
            if not text_parts:
                body = soup.find('body')
                if body:
                    paragraphs = body.find_all('p')
                    for p in paragraphs[:20]:
                        text = p.get_text(strip=True)
                        if len(text) > 40:
                            text_parts.append(text)
            
            # Объединяем текст
            if text_parts:
                full_text = ' '.join(text_parts)
                
                # Очистка
                full_text = re.sub(r'\s+', ' ', full_text)
                full_text = re.sub(r'Читайте также.*?(?=\.|$)', '', full_text, flags=re.IGNORECASE)
                full_text = re.sub(r'Фото:.*?(?=\.|$)', '', full_text, flags=re.IGNORECASE)
                full_text = re.sub(r'Видео:.*?(?=\.|$)', '', full_text, flags=re.IGNORECASE)
                
                # Убираем дубликаты картинок
                unique_images = []
                seen = set()
                for img in images:
                    if img not in seen:
                        seen.add(img)
                        unique_images.append(img)
                
                self.log(f"Текст: {len(full_text)} символов, Картинок: {len(unique_images)}", "TEXT")
                self.stats['text_found'] += 1
                if unique_images:
                    self.stats['with_images'] += 1
                
                return full_text, unique_images[:CONFIG['MAX_IMAGES']]
            
            return None, []
            
        except Exception as e:
            self.log(f"Ошибка загрузки: {e}", "ERROR")
            self.stats['errors'] += 1
            return None, []
    
    def extract_text_from_rss(self, entry) -> Optional[str]:
        """Запасной вариант - текст из RSS"""
        text_candidates = []
        
        # Проверяем все поля
        for field in ['content', 'content_encoded', 'summary_detail', 'description', 'summary']:
            if hasattr(entry, field):
                val = getattr(entry, field)
                if isinstance(val, list):
                    for item in val:
                        if hasattr(item, 'value') and item.value:
                            text_candidates.append(str(item.value))
                elif hasattr(val, 'value') and val.value:
                    text_candidates.append(str(val.value))
                elif isinstance(val, str):
                    text_candidates.append(val)
        
        # Выбираем самый длинный
        best_text = None
        best_len = 0
        
        for raw in text_candidates:
            clean = re.sub(r'<[^>]+>', ' ', raw)
            clean = html.unescape(clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
            
            if len(clean) > best_len:
                best_len = len(clean)
                best_text = clean
        
        if best_text and best_len > 100:
            return best_text
        return None
    
    def ai_rewrite(self, text: str, title: str) -> str:
        """ИИ переписывание"""
        if not CONFIG['USE_AI'] or len(text) < 200:
            return text
        
        try:
            prompt = f"""Перепиши эту новость своими словами, сохранив все факты.
Напиши связный текст из 4-5 предложений.

Заголовок: {title}
Текст: {text[:1500]}

Переписанный текст:"""
            
            headers = {
                "Authorization": f"Bearer {CONFIG['AI_API_KEY']}",
                "Content-Type": "application/json",
            }
            
            data = {
                "model": CONFIG['AI_MODEL'],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(CONFIG['AI_API_URL'], headers=headers, json=data, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                rewritten = result["choices"][0]["message"]["content"]
                rewritten = re.sub(r'\s+', ' ', rewritten).strip()
                return rewritten
        except:
            pass
        
        return text
    
    def run(self):
        print("\n" + "="*70)
        print("🚀 ФИНАЛЬНЫЙ СБОРЩИК НОВОСТЕЙ")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🤖 ИИ: {'АКТИВЕН' if CONFIG['USE_AI'] else 'ОТКЛЮЧЕН'}")
        print("="*70 + "\n")
        
        os.makedirs('public', exist_ok=True)
        json_path = 'public/news_data_v3.json'
        
        # Загружаем старые новости
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
        
        # Обрабатываем источники
        for category, feeds in RSS_FEEDS.items():
            self.log(f"\n📊 КАТЕГОРИЯ: {category}")
            
            for feed_url in feeds:
                try:
                    feed = feedparser.parse(feed_url)
                    
                    if not feed.entries:
                        continue
                    
                    self.log(f"📡 {feed_url.split('/')[-1]}: {len(feed.entries)} записей")
                    
                    for idx, entry in enumerate(feed.entries[:CONFIG['MAX_ARTICLES_PER_FEED']], 1):
                        self.total_processed += 1
                        
                        if entry.link in self.existing_links:
                            self.stats['already_exists'] += 1
                            continue
                        
                        self.log(f"[{idx}] {entry.title[:70]}...")
                        
                        # 1. Пробуем загрузить страницу
                        full_text, images = self.extract_text_from_page(entry.link)
                        
                        # 2. Если не получилось - берем из RSS
                        if not full_text:
                            self.log("Пробую текст из RSS...", "WARNING")
                            full_text = self.extract_text_from_rss(entry)
                        
                        # 3. Если все равно нет текста - используем заголовок
                        if not full_text:
                            full_text = entry.title
                            self.log("Использую только заголовок", "WARNING")
                        
                        # Применяем ИИ
                        if CONFIG['USE_AI'] and len(full_text) > 200:
                            full_text = self.ai_rewrite(full_text, entry.title)
                        
                        # Форматируем в HTML
                        sentences = re.split(r'(?<=[.!?])\s+', full_text)
                        content_html = '\n'.join([f'<p>{s.strip()}</p>' for s in sentences[:6] if s.strip()])
                        
                        if not content_html:
                            content_html = f'<p>{full_text[:300]}...</p>'
                        
                        # Создаем запись
                        news_item = {
                            'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                            'title': entry.title.strip()[:250],
                            'description': full_text[:200] + '...' if len(full_text) > 200 else full_text,
                            'content': content_html,
                            'category': category,
                            'images': images,
                            'originalLink': entry.link,
                            'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        self.all_news.append(news_item)
                        self.existing_links.add(entry.link)
                        self.new_count += 1
                        
                        self.log(f"✅ СОХРАНЕНО | Текст: {len(full_text)} символов")
                        
                        time.sleep(CONFIG['REQUEST_DELAY'])
                        
                except Exception as e:
                    self.log(f"Ошибка: {e}", "ERROR")
                    self.stats['errors'] += 1
                    continue
        
        # Сохраняем
        self.all_news.sort(key=lambda x: x['timestamp'], reverse=True)
        
        if len(self.all_news) > CONFIG['MAX_NEWS_TOTAL']:
            self.all_news = self.all_news[:CONFIG['MAX_NEWS_TOTAL']]
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_news, f, ensure_ascii=False, indent=2)
        
        # Сохраняем версию
        version_data = {
            'version': datetime.now().timestamp(),
            'updated': datetime.now().isoformat(),
            'total': len(self.all_news),
            'new': self.new_count,
            'processed': self.total_processed,
            **self.stats
        }
        
        with open('public/version.json', 'w', encoding='utf-8') as f:
            json.dump(version_data, f, ensure_ascii=False, indent=2)
        
        # Итоги
        print("\n" + "="*70)
        print("📊 ИТОГИ РАБОТЫ:")
        print(f"   Всего новостей: {len(self.all_news)}")
        print(f"   Новых добавлено: {self.new_count}")
        print(f"   Всего обработано: {self.total_processed}")
        print(f"   Уже было в базе: {self.stats['already_exists']}")
        print(f"   Страниц загружено: {self.stats['page_loaded']}")
        print(f"   Текст найден: {self.stats['text_found']}")
        print(f"   С картинками: {self.stats['with_images']}")
        print(f"   Ошибок: {self.stats['errors']}")
        print("="*70)

if __name__ == '__main__':
    try:
        collector = NewsCollector()
        collector.run()
    except KeyboardInterrupt:
        print("\n👋 Остановлено пользователем")
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()