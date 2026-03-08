#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ФИНАЛЬНАЯ ВЕРСИЯ - ТЕКСТ ПРОХОДИТ ТОЛЬКО ЧЕРЕЗ ИИ
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
    'MAX_ARTICLES_PER_FEED': 20,
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

# РАСШИРЕННЫЕ ИСТОЧНИКИ
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
        'https://habr.com/ru/rss/news/?fl=ru',
    ],
    'Авто': [
        'https://lenta.ru/rss/news/auto',
        'https://ria.ru/export/rss2/auto/index.xml',
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
    """Сборщик новостей"""
    
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
    
    def extract_text_from_page(self, url: str) -> Tuple[Optional[str], List[str]]:
        """Загрузка страницы и извлечение текста"""
        try:
            self.log(f"Загрузка страницы...", "LOAD")
            
            response = self.session.get(url, timeout=CONFIG['TIMEOUT'])
            if response.status_code != 200:
                return None, []
            
            self.stats['page_loaded'] += 1
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Удаляем мусор
            for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            # Ищем картинки
            images = []
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src and re.search(r'\.(jpg|jpeg|png|webp)', src.lower()):
                    if not re.search(r'(logo|icon|avatar|favicon|pixel|spacer)', src.lower()):
                        if src.startswith('//'):
                            src = 'https:' + src
                        images.append(src)
            
            # Ищем текст
            text_parts = []
            
            # Ищем статью
            article = soup.find('article')
            if article:
                paragraphs = article.find_all('p')
                for p in paragraphs[:20]:
                    text = p.get_text(strip=True)
                    if len(text) > 40:
                        text_parts.append(text)
            
            # Если не нашли, берем все параграфы
            if not text_parts:
                paragraphs = soup.find_all('p')
                for p in paragraphs[:20]:
                    text = p.get_text(strip=True)
                    if len(text) > 50:
                        text_parts.append(text)
            
            if text_parts:
                full_text = ' '.join(text_parts)
                
                # МИНИМАЛЬНАЯ очистка (только HTML)
                full_text = re.sub(r'<[^>]+>', ' ', full_text)
                full_text = html.unescape(full_text)
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                
                # Убираем дубликаты картинок
                unique_images = []
                seen = set()
                for img in images:
                    if img not in seen:
                        seen.add(img)
                        unique_images.append(img)
                
                if unique_images:
                    self.stats['with_images'] += 1
                
                self.log(f"Текст: {len(full_text)} символов, Картинок: {len(unique_images)}", "TEXT")
                self.stats['text_found'] += 1
                
                return full_text, unique_images[:CONFIG['MAX_IMAGES']]
            
            return None, []
            
        except Exception as e:
            self.stats['errors'] += 1
            return None, []
    
    def ai_rewrite(self, text: str, title: str, category: str) -> str:
        """ИИ переписывание - УДАЛЯЕТ УПОМИНАНИЯ САЙТОВ И ДЕЛАЕТ ТЕКСТ УНИКАЛЬНЫМ"""
        if not CONFIG['USE_AI'] or len(text) < 200:
            return text
        
        try:
            self.log("🤖 ИИ обрабатывает текст...", "AI")
            
            prompt = f"""Ты профессиональный журналист. Перепиши эту новость полностью своими словами.

ВАЖНЫЕ ИНСТРУКЦИИ:
1. Удали все упоминания других сайтов (РИА, ТАСС, Лента, Интерфакс и т.д.)
2. Удали фразы типа "об этом сообщает", "по информации", "как пишет"
3. Напиши связный текст из 4-6 предложений
4. Сохрани все важные факты
5. Текст должен быть уникальным (не копией оригинала)

Категория: {category}
Заголовок: {title}

Оригинальный текст:
{text[:2000]}

Твой переписанный текст (только текст статьи, без пояснений):"""
            
            headers = {"Authorization": f"Bearer {CONFIG['AI_API_KEY']}"}
            data = {
                "model": CONFIG['AI_MODEL'],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,  # Выше температура = больше изменений
                "max_tokens": 1000
            }
            
            response = requests.post(CONFIG['AI_API_URL'], headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                rewritten = result["choices"][0]["message"]["content"]
                
                # Базовая очистка
                rewritten = re.sub(r'\s+', ' ', rewritten).strip()
                
                self.stats['ai_processed'] += 1
                self.log(f"✅ ИИ завершил: {len(rewritten)} символов", "AI")
                
                return rewritten
            else:
                self.log(f"⚠️ Ошибка ИИ: {response.status_code}", "WARNING")
                return text
                
        except Exception as e:
            self.log(f"⚠️ Ошибка ИИ: {e}", "WARNING")
            return text
    
    def run(self):
        print("\n" + "="*70)
        print("🚀 ФИНАЛЬНЫЙ СБОРЩИК НОВОСТЕЙ")
        print("🤖 ТОЛЬКО ИИ - текст всегда меняется")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")
        
        os.makedirs('public', exist_ok=True)
        json_path = 'public/news_data_v3.json'
        
        # Загружаем старые
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.all_news = json.load(f)
                    for item in self.all_news:
                        if item.get('originalLink'):
                            self.existing_links.add(item['originalLink'])
                        for img in item.get('images', []):
                            self.seen_images.add(img.split('?')[0])
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
                        
                        # Загружаем страницу
                        full_text, images = self.extract_text_from_page(entry.link)
                        
                        # Если не получилось - используем заголовок
                        if not full_text:
                            full_text = entry.title
                            self.log("Использую заголовок", "WARNING")
                        
                        # 100% ПРОГОНЯЕМ ЧЕРЕЗ ИИ
                        if CONFIG['USE_AI'] and len(full_text) > 100:
                            full_text = self.ai_rewrite(full_text, entry.title, category)
                        
                        # Форматируем в HTML
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
        print(f"   Уже было: {self.stats['already_exists']}")
        print(f"   Страниц загружено: {self.stats['page_loaded']}")
        print(f"   Текст найден: {self.stats['text_found']}")
        print(f"   Обработано ИИ: {self.stats['ai_processed']}")
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