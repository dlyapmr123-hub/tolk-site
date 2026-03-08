#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
СУПЕР-СБОРЩИК - НАЙДЕТ ТЕКСТ В ЛЮБОМ МЕСТЕ
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

# Конфигурация
CONFIG = {
    'TIMEOUT': 10,
    'MAX_ARTICLES_PER_FEED': 30,
    'REQUEST_DELAY': 0.2,
    'MAX_IMAGES': 3,
    'MIN_TEXT_LENGTH': 100,  # Уменьшил минимум
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
        'https://ria.ru/export/rss2/politics/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://lenta.ru/rss/news/politics',
    ],
    'Экономика': [
        'https://ria.ru/export/rss2/economy/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://lenta.ru/rss/news/economics',
    ],
    'Технологии': [
        'https://ria.ru/export/rss2/technology/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://lenta.ru/rss/news/technology',
        'https://www.interfax.ru/rss.asp',
    ],
    'Авто': [
        'https://ria.ru/export/rss2/auto/index.xml',
        'https://lenta.ru/rss/news/auto',
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',
    ],
    'Культура': [
        'https://ria.ru/export/rss2/culture/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://lenta.ru/rss/news/art',
    ],
    'Спорт': [
        'https://ria.ru/export/rss2/sport/index.xml',
        'https://tass.ru/rss/v2.xml',
        'https://lenta.ru/rss/news/sport',
        'https://www.championat.com/news/rss/',
    ]
}

class SuperCollector:
    """СУПЕР-СБОРЩИК - найдет текст любой ценой"""
    
    def __init__(self):
        self.existing_links = set()
        self.all_news = []
        self.new_count = 0
        self.total_processed = 0
        self.stats = {
            'text_found': 0,
            'no_text': 0,
            'already_exists': 0,
            'with_images': 0
        }
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji = {"INFO": "📌", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "TEXT": "📝"}.get(level, "📌")
        print(f"{emoji} [{timestamp}] {message}")
    
    def extract_text_brutal(self, entry) -> Optional[str]:
        """
        ЖЕСТОКИЙ ПОИСК ТЕКСТА - проверит ВСЕ возможные поля
        """
        text_candidates = []
        
        # 1. ПРОВЕРЯЕМ ВСЕ ПОЛЯ RSS
        fields_to_check = [
            'content', 'content_encoded', 'summary_detail', 
            'description', 'summary', 'title_detail',
            'subtitle', 'subtitle_detail', 'info', 'info_detail',
            'tagline', 'tagline_detail', 'rights', 'rights_detail'
        ]
        
        for field in fields_to_check:
            try:
                if hasattr(entry, field):
                    field_value = getattr(entry, field)
                    
                    # Если это список (как content)
                    if isinstance(field_value, list):
                        for item in field_value:
                            if hasattr(item, 'value') and item.value:
                                text_candidates.append(str(item.value))
                            elif isinstance(item, dict) and item.get('value'):
                                text_candidates.append(str(item['value']))
                            elif isinstance(item, str):
                                text_candidates.append(item)
                    
                    # Если это объект с value
                    elif hasattr(field_value, 'value') and field_value.value:
                        text_candidates.append(str(field_value.value))
                    
                    # Если это просто строка
                    elif isinstance(field_value, str):
                        text_candidates.append(field_value)
                    
                    # Если это словарь
                    elif isinstance(field_value, dict):
                        for key in ['value', 'content', 'text', 'data']:
                            if key in field_value and field_value[key]:
                                text_candidates.append(str(field_value[key]))
            except:
                pass
        
        # 2. ПРОВЕРЯЕМ ВСЕ АТРИБУТЫ (на всякий случай)
        for attr_name in dir(entry):
            if not attr_name.startswith('_') and attr_name not in fields_to_check:
                try:
                    attr_value = getattr(entry, attr_name)
                    if isinstance(attr_value, str) and len(attr_value) > 100:
                        text_candidates.append(attr_value)
                except:
                    pass
        
        # 3. ОЧИЩАЕМ И ВЫБИРАЕМ ЛУЧШИЙ ТЕКСТ
        best_text = None
        best_length = 0
        
        for raw_text in text_candidates:
            if not raw_text or not isinstance(raw_text, str):
                continue
            
            # Очищаем от HTML
            clean = re.sub(r'<[^>]+>', ' ', raw_text)
            clean = html.unescape(clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
            
            # Убираем мусор
            clean = re.sub(r'Читайте также.*?(?=\.|$)', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'Фото:.*?(?=\.|$)', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'Видео:.*?(?=\.|$)', '', clean, flags=re.IGNORECASE)
            
            length = len(clean)
            
            if length > best_length:
                best_length = length
                best_text = clean
        
        # 4. ЕСЛИ НИЧЕГО НЕ НАШЛИ - ИСПОЛЬЗУЕМ ТАЙТЛ
        if not best_text and hasattr(entry, 'title'):
            best_text = entry.title
            best_length = len(best_text)
            self.log(f"Использую только заголовок: {best_text[:50]}...", "WARNING")
        
        if best_text and best_length > 50:
            self.log(f"Найден текст: {best_length} символов", "TEXT")
            self.stats['text_found'] += 1
            return best_text
        
        self.stats['no_text'] += 1
        return None
    
    def extract_images_brutal(self, entry) -> List[str]:
        """Поиск картинок везде"""
        images = []
        
        # media:content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('url'):
                    url = media['url']
                    if url.startswith('//'):
                        url = 'https:' + url
                    images.append(url)
        
        # links
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('image/'):
                    images.append(link.get('href'))
        
        # Ищем в тексте
        for field in ['summary', 'description', 'content', 'content_encoded']:
            if hasattr(entry, field):
                text = str(getattr(entry, field))
                img_matches = re.findall(r'<img[^>]+src="([^">]+)"', text)
                for url in img_matches:
                    if url.startswith('//'):
                        url = 'https:' + url
                    images.append(url)
        
        # Убираем дубликаты
        unique = []
        seen = set()
        for img in images:
            if img not in seen:
                seen.add(img)
                unique.append(img)
        
        return unique[:CONFIG['MAX_IMAGES']]
    
    def ai_rewrite(self, text, title):
        """Быстрый ИИ"""
        if not CONFIG['USE_AI'] or len(text) < 200:
            return text
        
        try:
            prompt = f"""Перепиши: {title}
            
Оригинал: {text[:1000]}

Краткий пересказ (3-4 предложения):"""
            
            headers = {"Authorization": f"Bearer {CONFIG['AI_API_KEY']}"}
            data = {
                "model": CONFIG['AI_MODEL'],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(CONFIG['AI_API_URL'], headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                rewritten = result["choices"][0]["message"]["content"]
                return re.sub(r'\s+', ' ', rewritten).strip()
        except:
            pass
        
        return text
    
    def run(self):
        print("\n" + "="*70)
        print("🚀 СУПЕР-СБОРЩИК ЗАПУЩЕН")
        print("="*70)
        
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
                self.log(f"Загружено {len(self.all_news)} старых новостей")
            except:
                self.all_news = []
        
        # Собираем новые
        for category, feeds in RSS_FEEDS.items():
            for feed_url in feeds:
                try:
                    self.log(f"\n📡 {category} - {feed_url.split('/')[-1]}")
                    feed = feedparser.parse(feed_url)
                    
                    entries = list(feed.entries)[:CONFIG['MAX_ARTICLES_PER_FEED']]
                    
                    for idx, entry in enumerate(entries, 1):
                        self.total_processed += 1
                        
                        if entry.link in self.existing_links:
                            self.stats['already_exists'] += 1
                            continue
                        
                        self.log(f"[{idx}/{len(entries)}] {entry.title[:60]}...")
                        
                        # ЖЕСТКИЙ ПОИСК ТЕКСТА
                        full_text = self.extract_text_brutal(entry)
                        
                        if not full_text:
                            self.log(f"❌ Текст не найден! Но это невозможно!", "ERROR")
                            continue
                        
                        # Картинки
                        images = self.extract_images_brutal(entry)
                        if images:
                            self.stats['with_images'] += 1
                            self.log(f"📸 Картинок: {len(images)}")
                        
                        # ИИ
                        if CONFIG['USE_AI']:
                            full_text = self.ai_rewrite(full_text, entry.title)
                        
                        # Форматируем
                        sentences = re.split(r'(?<=[.!?])\s+', full_text)
                        content_html = '\n'.join([f'<p>{s.strip()}</p>' for s in sentences[:6] if s.strip()])
                        
                        if not content_html:
                            content_html = f'<p>{full_text[:300]}</p>'
                        
                        # Создаем
                        news_item = {
                            'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                            'title': entry.title.strip(),
                            'description': full_text[:200] + '...',
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
                    continue
        
        # Сохраняем
        self.all_news.sort(key=lambda x: x['timestamp'], reverse=True)
        
        if len(self.all_news) > CONFIG['MAX_NEWS_TOTAL']:
            self.all_news = self.all_news[:CONFIG['MAX_NEWS_TOTAL']]
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_news, f, ensure_ascii=False, indent=2)
        
        # Итоги
        print("\n" + "="*70)
        print("📊 ИТОГИ:")
        print(f"   Всего новостей: {len(self.all_news)}")
        print(f"   Новых добавлено: {self.new_count}")
        print(f"   Всего обработано: {self.total_processed}")
        print(f"   Уже было: {self.stats['already_exists']}")
        print(f"   Текст найден: {self.stats['text_found']}")
        print(f"   С картинками: {self.stats['with_images']}")
        print("="*70)

if __name__ == '__main__':
    collector = SuperCollector()
    collector.run()