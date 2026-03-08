#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ФИНАЛЬНАЯ ВЕРСИЯ - ИСПРАВЛЕНИЕ ВСЕХ ПРОБЛЕМ:
1. Убираем рекламу (РИА Новости, Лента.ру и т.д.)
2. Исправляем пробелы (слова слипаются)
3. Убираем дубликаты картинок
4. Чистим текст от мусора
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

class TextCleaner:
    """ОЧИСТКА ТЕКСТА ОТ МУСОРА"""
    
    @staticmethod
    def fix_spaces(text: str) -> str:
        """Исправляет слипшиеся слова"""
        # Вставляем пробелы между словами где их нет
        # Например: "Карпинасделалавыбор" -> "Карпина сделала выбор"
        text = re.sub(r'([а-яА-Я])([А-Я][а-я])', r'\1 \2', text)
        text = re.sub(r'([a-zA-Z])([A-Z][a-z])', r'\1 \2', text)
        return text
    
    @staticmethod
    def remove_garbage(text: str) -> str:
        """Удаляет рекламу и мусор"""
        
        # СПИСОК МУСОРНЫХ ФРАЗ ДЛЯ УДАЛЕНИЯ
        garbage_phrases = [
            # Названия источников
            r'РИА Новости\.?',
            r'ТАСС\.?',
            r'Лента\.?ру',
            r'Интерфакс\.?',
            r'РБК\.?',
            r'Газета\.?ру',
            r'Коммерсантъ\.?',
            r'Ведомости\.?',
            r'Известия\.?',
            r'МК\.?',
            r'АиФ\.?',
            r'Life\.?',
            r'RT\.?',
            r'Sputnik\.?',
            
            # Фразы-паразиты
            r'Об этом сообщает корреспондент.*?\.',
            r'Как сообщает.*?\.',
            r'По информации.*?\.',
            r'По данным.*?\.',
            r'Передает.*?\.',
            r'Со ссылкой на.*?\.',
            r'Источник сообщает.*?\.',
            r'Стало известно.*?\.',
            
            # Призывы и реклама
            r'Подпишитесь.*?\.',
            r'Следите за новостями.*?\.',
            r'Читайте также.*?\.',
            r'Смотрите также.*?\.',
            r'По теме.*?\.',
            r'Фото:.*?\.',
            r'Видео:.*?\.',
            r'Ссылка:.*?\.',
            r'Источник:.*?\.',
            
            # Соцсети
            r'Telegram.*?канал',
            r'VKontakte',
            r'Вконтакте',
            r'YouTube',
            r'Instagram',
            r'Twitter',
            r'Facebook',
            
            # Юридическое
            r'©.*?\d{4}',
            r'Все права защищены',
            r'18\+',
            r'16\+',
            r'12\+',
            r'cookie',
            r'конфиденциальность',
            r'политика обработки',
        ]
        
        for pattern in garbage_phrases:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text
    
    @staticmethod
    def clean_article_text(text: str) -> str:
        """ПОЛНАЯ ОЧИСТКА ТЕКСТА"""
        if not text:
            return ""
        
        # 1. Удаляем HTML теги
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # 2. Декодируем HTML сущности
        text = html.unescape(text)
        
        # 3. Удаляем мусорные фразы
        text = TextCleaner.remove_garbage(text)
        
        # 4. Удаляем лишние пробелы
        text = re.sub(r'\s+', ' ', text)
        
        # 5. Исправляем слипшиеся слова
        text = TextCleaner.fix_spaces(text)
        
        # 6. Чистим пунктуацию
        text = re.sub(r'\.{3,}', '.', text)
        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'\s+\.', '.', text)
        text = re.sub(r'\.\s+', '. ', text)
        
        # 7. Убираем пробелы перед знаками препинания
        text = re.sub(r'\s+([,.;:!?])', r'\1', text)
        
        # 8. Убираем множественные пробелы
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

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
            'duplicate_images_removed': 0
        }
        
        self.seen_images = set()  # Для отслеживания дубликатов картинок
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji = {
            "INFO": "📌", "SUCCESS": "✅", "WARNING": "⚠️", 
            "ERROR": "❌", "LOAD": "📥", "CLEAN": "🧹",
            "AI": "🤖", "IMAGE": "📸", "TEXT": "📝"
        }.get(level, "📌")
        print(f"{emoji} [{timestamp}] {message}")
    
    def get_unique_images(self, images: List[str]) -> List[str]:
        """Убирает дубликаты картинок"""
        unique = []
        for img in images:
            # Нормализуем URL (убираем параметры)
            base_url = img.split('?')[0]
            
            if base_url not in self.seen_images:
                self.seen_images.add(base_url)
                unique.append(img)
            else:
                self.stats['duplicate_images_removed'] += 1
        
        return unique[:CONFIG['MAX_IMAGES']]
    
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
            
            # Пробуем найти статью
            article = (soup.find('article') or 
                      soup.find('main') or 
                      soup.find('div', class_=re.compile(r'article|content|text|post|news', re.I)))
            
            if article:
                paragraphs = article.find_all('p')
                for p in paragraphs[:15]:
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
                
                # ОЧИЩАЕМ ТЕКСТ
                full_text = TextCleaner.clean_article_text(full_text)
                
                # Убираем дубликаты картинок
                unique_images = self.get_unique_images(images)
                
                if unique_images:
                    self.stats['with_images'] += 1
                
                self.log(f"Текст: {len(full_text)} символов, Картинок: {len(unique_images)}", "TEXT")
                self.stats['text_found'] += 1
                
                return full_text, unique_images
            
            return None, []
            
        except Exception as e:
            self.stats['errors'] += 1
            return None, []
    
    def ai_rewrite(self, text: str, title: str) -> str:
        """ИИ переписывание"""
        if not CONFIG['USE_AI'] or len(text) < 200:
            return text
        
        try:
            self.log("ИИ обрабатывает...", "AI")
            
            prompt = f"""Перепиши эту новость своими словами. 
Сохрани все факты, но убери упоминания других сайтов (РИА, ТАСС, Лента и т.д.).
Напиши чистый, грамотный текст из 4-5 предложений.

Заголовок: {title}
Текст: {text[:1500]}

Переписанный текст:"""
            
            headers = {"Authorization": f"Bearer {CONFIG['AI_API_KEY']}"}
            data = {
                "model": CONFIG['AI_MODEL'],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 600
            }
            
            response = requests.post(CONFIG['AI_API_URL'], headers=headers, json=data, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                rewritten = result["choices"][0]["message"]["content"]
                rewritten = TextCleaner.clean_article_text(rewritten)
                return rewritten
        except:
            pass
        
        return text
    
    def run(self):
        print("\n" + "="*70)
        print("🚀 ФИНАЛЬНЫЙ СБОРЩИК НОВОСТЕЙ")
        print("🧹 С очисткой текста и удалением рекламы")
        print("📸 Без дубликатов картинок")
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
                        # Собираем уже использованные картинки
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
                        
                        # Применяем ИИ
                        if CONFIG['USE_AI'] and len(full_text) > 200:
                            full_text = self.ai_rewrite(full_text, entry.title)
                        
                        # Финальная очистка
                        full_text = TextCleaner.clean_article_text(full_text)
                        
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
        
        # Итоги
        print("\n" + "="*70)
        print("📊 ИТОГИ РАБОТЫ:")
        print(f"   Всего новостей: {len(self.all_news)}")
        print(f"   Новых добавлено: {self.new_count}")
        print(f"   Всего обработано: {self.total_processed}")
        print(f"   Уже было: {self.stats['already_exists']}")
        print(f"   Страниц загружено: {self.stats['page_loaded']}")
        print(f"   Текст найден: {self.stats['text_found']}")
        print(f"   С картинками: {self.stats['with_images']}")
        print(f"   Дублей картинок убрано: {self.stats['duplicate_images_removed']}")
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