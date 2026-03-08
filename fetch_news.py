#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ПРОФЕССИОНАЛЬНЫЙ СБОРЩИК НОВОСТЕЙ ДЛЯ ТОЛК
Версия: 3.0
Источники: РИА Новости, ТАСС, Lenta.ru, RBC, Interfax
Особенности: Полный текст, ИИ-рерайт, картинки, автообновление
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
from urllib.parse import urlparse

import requests

# Конфигурация
CONFIG = {
    'TIMEOUT': 15,
    'MAX_ARTICLES_PER_FEED': 30,
    'REQUEST_DELAY': 0.5,
    'MAX_IMAGES': 3,
    'MIN_TEXT_LENGTH': 300,
    'MAX_NEWS_TOTAL': 500,
    'USE_AI': True,
    'AI_MODEL': 'gpt-3.5-turbo',
    'AI_API_URL': 'https://openrouter.ai/api/v1/chat/completions',
    'AI_API_KEY': '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',
    'SITE_URL': 'https://tolk-1.web.app'
}

# РАБОЧИЕ ИСТОЧНИКИ RSS (протестированы)
RSS_FEEDS = {
    'Политика': [
        'https://ria.ru/export/rss2/politics/index.xml',      # РИА Новости - есть текст
        'https://tass.ru/rss/v2.xml',                          # ТАСС - есть текст
        'https://lenta.ru/rss/news/politics',                  # Lenta.ru - быстро
        'https://www.rbc.ru/rss/',                             # RBC - экономика/политика
    ],
    'Экономика': [
        'https://ria.ru/export/rss2/economy/index.xml',        # РИА
        'https://tass.ru/rss/v2.xml',                          # ТАСС
        'https://lenta.ru/rss/news/economics',                 # Lenta.ru
        'https://www.rbc.ru/rss/',                             # RBC
    ],
    'Технологии': [
        'https://ria.ru/export/rss2/technology/index.xml',     # РИА
        'https://tass.ru/rss/v2.xml',                          # ТАСС
        'https://lenta.ru/rss/news/technology',                # Lenta.ru
        'https://www.interfax.ru/rss.asp',                     # Interfax
    ],
    'Авто': [
        'https://ria.ru/export/rss2/auto/index.xml',           # РИА Авто
        'https://lenta.ru/rss/news/auto',                      # Lenta.ru Авто
    ],
    'Киберспорт': [
        'https://www.cybersport.ru/rss',                       # Cybersport
    ],
    'Культура': [
        'https://ria.ru/export/rss2/culture/index.xml',        # РИА
        'https://tass.ru/rss/v2.xml',                          # ТАСС
        'https://lenta.ru/rss/news/art',                       # Lenta.ru
    ],
    'Спорт': [
        'https://ria.ru/export/rss2/sport/index.xml',          # РИА
        'https://tass.ru/rss/v2.xml',                          # ТАСС
        'https://lenta.ru/rss/news/sport',                     # Lenta.ru
        'https://www.championat.com/news/rss/',                # Championat
    ]
}

class NewsCollector:
    """Профессиональный сборщик новостей"""
    
    def __init__(self):
        self.existing_links = set()
        self.all_news = []
        self.new_count = 0
        self.total_processed = 0
        self.stats = {
            'no_text': 0,
            'too_short': 0,
            'already_exists': 0,
            'with_images': 0
        }
        
        # Настройка вывода
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(line_buffering=True)
    
    def log(self, message: str, level: str = "INFO"):
        """Красивый вывод логов"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        emoji = {
            "INFO": "📌", "SUCCESS": "✅", "WARNING": "⚠️", 
            "ERROR": "❌", "DEBUG": "🔍", "AI": "🤖", "IMAGE": "📸"
        }.get(level, "📌")
        print(f"{emoji} [{timestamp}] {message}")
    
    def clean_html(self, text: str) -> str:
        """Очистка HTML от мусора"""
        if not text:
            return ""
        
        # Удаляем HTML теги
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Декодируем HTML сущности
        text = html.unescape(text)
        
        # Удаляем лишние пробелы
        text = re.sub(r'\s+', ' ', text)
        
        # Удаляем мусорные фразы
        garbage_patterns = [
            r'Читайте также:.*?(?=\.|$)',
            r'Фото:.*?(?=\.|$)',
            r'Видео:.*?(?=\.|$)',
            r'Смотрите также.*?(?=\.|$)',
            r'По теме.*?(?=\.|$)',
            r'Источник:.*?(?=\.|$)',
            r'Ссылка:.*?(?=\.|$)',
            r'Telegram',
            r'VK',
            r'Вконтакте',
            r'YouTube',
            r'Instagram',
            r'Twitter',
            r'Facebook',
            r'реклама',
            r'cookie',
            r'конфиденциальность',
            r'все права защищены',
            r'©.*?\d{4}',
        ]
        
        for pattern in garbage_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Чистка пунктуации
        text = re.sub(r'\.{3,}', '.', text)
        text = re.sub(r'\.{2,}', '.', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def extract_text_from_entry(self, entry) -> Optional[str]:
        """Извлечение текста из записи RSS"""
        
        # Поле content (самое полное)
        if hasattr(entry, 'content'):
            for content in entry.content:
                if content.get('value'):
                    text = self.clean_html(content['value'])
                    if len(text) > CONFIG['MIN_TEXT_LENGTH']:
                        return text
        
        # Поле content_encoded
        if hasattr(entry, 'content_encoded'):
            text = self.clean_html(entry.content_encoded)
            if len(text) > CONFIG['MIN_TEXT_LENGTH']:
                return text
        
        # Поле summary_detail
        if hasattr(entry, 'summary_detail') and hasattr(entry.summary_detail, 'value'):
            text = self.clean_html(entry.summary_detail.value)
            if len(text) > CONFIG['MIN_TEXT_LENGTH']:
                return text
        
        # Поле description
        if hasattr(entry, 'description'):
            text = self.clean_html(entry.description)
            if len(text) > CONFIG['MIN_TEXT_LENGTH']:
                return text
        
        # Поле summary
        if hasattr(entry, 'summary'):
            text = self.clean_html(entry.summary)
            if len(text) > CONFIG['MIN_TEXT_LENGTH']:
                return text
        
        return None
    
    def extract_images_from_entry(self, entry) -> List[str]:
        """Извлечение картинок из записи"""
        images = []
        
        # Из media:content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('url'):
                    url = media['url']
                    if url.startswith('//'):
                        url = 'https:' + url
                    images.append(url)
        
        # Из links
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('image/'):
                    images.append(link.get('href'))
        
        # Из summary (ищем img теги)
        if hasattr(entry, 'summary'):
            img_matches = re.findall(r'<img[^>]+src="([^">]+)"', entry.summary)
            for url in img_matches:
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
        
        # Убираем дубликаты
        unique_images = []
        seen = set()
        for img in images:
            if img not in seen:
                seen.add(img)
                unique_images.append(img)
        
        return unique_images[:CONFIG['MAX_IMAGES']]
    
    def ai_rewrite(self, text: str, title: str, category: str) -> str:
        """Переписывание текста через ИИ"""
        if not CONFIG['USE_AI'] or len(text) < 300:
            return text
        
        try:
            self.log(f"ИИ обрабатывает текст...", "AI")
            
            # Берем часть текста для ИИ
            text_for_ai = text[:2000] if len(text) > 2000 else text
            
            prompt = f"""Ты профессиональный журналист. Перепиши эту новость своими словами, сохранив все факты.
Напиши связный, грамотный текст из 4-6 предложений. Убери рекламу и лишнюю информацию.

Категория: {category}
Заголовок: {title}

Текст новости:
{text_for_ai}

Переписанная новость:"""
            
            headers = {
                "Authorization": f"Bearer {CONFIG['AI_API_KEY']}",
                "Content-Type": "application/json",
                "HTTP-Referer": CONFIG['SITE_URL'],
                "X-Title": "Tolk News"
            }
            
            data = {
                "model": CONFIG['AI_MODEL'],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 800
            }
            
            response = requests.post(
                CONFIG['AI_API_URL'], 
                headers=headers, 
                json=data, 
                timeout=20
            )
            
            if response.status_code == 200:
                result = response.json()
                rewritten = result["choices"][0]["message"]["content"]
                rewritten = self.clean_html(rewritten)
                
                if len(rewritten) > 150:
                    self.log(f"ИИ завершил: {len(rewritten)} символов", "AI")
                    return rewritten
                else:
                    self.log(f"ИИ вернул короткий текст", "WARNING")
                    return text
            else:
                self.log(f"Ошибка ИИ: {response.status_code}", "WARNING")
                return text
                
        except Exception as e:
            self.log(f"Ошибка ИИ: {e}", "WARNING")
            return text
    
    def format_content_html(self, text: str) -> str:
        """Форматирование текста в HTML"""
        if not text:
            return "<p>Текст новости временно недоступен</p>"
        
        # Разбиваем на предложения
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        html_parts = []
        for sent in sentences[:8]:  # Максимум 8 предложений
            sent = sent.strip()
            if sent:
                # Убираем лишние точки в конце
                sent = re.sub(r'\.+$', '.', sent)
                if not sent.endswith('.'):
                    sent += '.'
                html_parts.append(f'<p>{sent}</p>')
        
        if not html_parts:
            return f"<p>{text[:300]}...</p>"
        
        return '\n'.join(html_parts)
    
    def load_existing_news(self, json_path: str):
        """Загрузка существующих новостей"""
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    self.all_news = json.load(f)
                    for item in self.all_news:
                        if item.get('originalLink'):
                            self.existing_links.add(item['originalLink'])
                self.log(f"Загружено {len(self.all_news)} старых новостей")
            except Exception as e:
                self.log(f"Ошибка загрузки: {e}", "WARNING")
                self.all_news = []
    
    def process_feed(self, category: str, feed_url: str):
        """Обработка одного RSS потока"""
        self.log(f"Чтение {feed_url}", "DEBUG")
        
        try:
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                self.log(f"Ошибка парсинга: {feed.bozo_exception}", "WARNING")
            
            entries_count = len(feed.entries)
            if entries_count == 0:
                self.log(f"Нет записей", "WARNING")
                return
            
            self.log(f"Найдено записей: {entries_count}")
            
            for idx, entry in enumerate(feed.entries[:CONFIG['MAX_ARTICLES_PER_FEED']], 1):
                self.total_processed += 1
                
                # Проверка на дубликат
                if entry.link in self.existing_links:
                    self.stats['already_exists'] += 1
                    continue
                
                self.log(f"[{idx}/{entries_count}] {entry.title[:80]}...")
                
                # Извлечение текста
                full_text = self.extract_text_from_entry(entry)
                
                if not full_text:
                    self.log(f"Текст не найден", "WARNING")
                    self.stats['no_text'] += 1
                    continue
                
                if len(full_text) < CONFIG['MIN_TEXT_LENGTH']:
                    self.log(f"Текст слишком короткий ({len(full_text)} символов)", "WARNING")
                    self.stats['too_short'] += 1
                    continue
                
                self.log(f"Текст: {len(full_text)} символов")
                
                # ИИ обработка
                if CONFIG['USE_AI']:
                    full_text = self.ai_rewrite(full_text, entry.title, category)
                
                # Картинки
                images = self.extract_images_from_entry(entry)
                if images:
                    self.stats['with_images'] += 1
                    self.log(f"Картинок: {len(images)}", "IMAGE")
                
                # Форматирование
                content_html = self.format_content_html(full_text)
                description = full_text[:200] + '...' if len(full_text) > 200 else full_text
                
                # Создание записи
                news_item = {
                    'id': hashlib.md5(entry.link.encode()).hexdigest()[:8],
                    'title': entry.title.strip()[:250],
                    'description': description,
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
                
                self.log(f"✅ СОХРАНЕНО")
                
                time.sleep(CONFIG['REQUEST_DELAY'])
                
        except Exception as e:
            self.log(f"Ошибка: {e}", "ERROR")
            traceback.print_exc()
    
    def run(self):
        """Основной запуск"""
        print("\n" + "="*70)
        print("🚀 ЗАПУСК ПРОФЕССИОНАЛЬНОГО СБОРЩИКА НОВОСТЕЙ")
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🤖 ИИ: {'АКТИВЕН' if CONFIG['USE_AI'] else 'ОТКЛЮЧЕН'}")
        print(f"📡 Источников: {sum(len(feeds) for feeds in RSS_FEEDS.values())}")
        print("="*70 + "\n")
        
        # Создание папки
        os.makedirs('public', exist_ok=True)
        
        json_path = 'public/news_data_v3.json'
        
        # Загрузка существующих новостей
        self.load_existing_news(json_path)
        
        # Обработка всех источников
        for category, feeds in RSS_FEEDS.items():
            print(f"\n📊 КАТЕГОРИЯ: {category}")
            print("-" * 40)
            
            for feed_url in feeds:
                self.process_feed(category, feed_url)
        
        # Сортировка и сохранение
        self.all_news.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Ограничение количества
        if len(self.all_news) > CONFIG['MAX_NEWS_TOTAL']:
            self.all_news = self.all_news[:CONFIG['MAX_NEWS_TOTAL']]
        
        # Сохранение JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_news, f, ensure_ascii=False, indent=2)
        
        # Сохранение версии
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
        print(f"   Нет текста: {self.stats['no_text']}")
        print(f"   Слишком короткие: {self.stats['too_short']}")
        print(f"   С картинками: {self.stats['with_images']}")
        print("="*70 + "\n")

def check_rss_feeds():
    """Проверка доступности RSS лент"""
    print("\n🔍 ПРОВЕРКА RSS ИСТОЧНИКОВ")
    print("-" * 40)
    
    working = 0
    total = 0
    
    for category, feeds in RSS_FEEDS.items():
        for feed_url in feeds:
            total += 1
            try:
                response = requests.get(feed_url, timeout=10)
                if response.status_code == 200:
                    print(f"✅ {category:12} | {feed_url[:50]}...")
                    working += 1
                else:
                    print(f"❌ {category:12} | Статус {response.status_code}")
            except:
                print(f"❌ {category:12} | Ошибка подключения")
    
    print("-" * 40)
    print(f"✅ Работает: {working}/{total}")
    print("-" * 40)

if __name__ == '__main__':
    try:
        # Сначала проверяем источники
        check_rss_feeds()
        
        # Запускаем сбор
        collector = NewsCollector()
        collector.run()
        
    except KeyboardInterrupt:
        print("\n👋 Остановлено пользователем")
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)