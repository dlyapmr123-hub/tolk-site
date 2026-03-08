#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import time
import hashlib
import random
import re
from datetime import datetime
import feedparser
import requests
from urllib.parse import urlparse

print("=== ЗАПУСК СКРИПТА ===")

# ============ ФУНКЦИЯ ПЕРЕФРАЗИРОВАНИЯ ============
def ai_rewrite_text(text):
    """Переписывает текст, делая его уникальным"""
    if not text or len(text) < 50:
        return text
    
    # Большой словарь синонимов
    synonyms = {
        'сказал': ['заявил', 'отметил', 'подчеркнул', 'сообщил', 'прокомментировал', 'выразил мнение'],
        'сообщил': ['проинформировал', 'уведомил', 'объявил', 'огласил', 'доложил', 'поделился информацией'],
        'произошло': ['случилось', 'состоялось', 'имело место', 'произошло событие', 'зафиксировано'],
        'начался': ['стартовал', 'открылся', 'запустился', 'взял старт', 'приступил к работе'],
        'закончился': ['завершился', 'финишировал', 'подошел к концу', 'окончился', 'прекратился'],
        'новый': ['свежий', 'актуальный', 'последний', 'современный', 'обновленный'],
        'важный': ['значительный', 'ключевой', 'главный', 'существенный', 'принципиальный'],
        'сегодня': ['в текущий день', 'на сегодняшний день', 'в настоящее время'],
        'вчера': ['минувший день', 'предыдущий день', 'накануне'],
        'завтра': ['в предстоящий день', 'на следующий день', 'в ближайшее время'],
        'россия': ['РФ', 'Российская Федерация', 'наша страна', 'отечество'],
        'российский': ['отечественный', 'российский', 'национальный'],
        'мир': ['планета', 'земной шар', 'вселенная', 'глобальное сообщество'],
        'люди': ['граждане', 'население', 'жители', 'общество'],
        'власть': ['правительство', 'администрация', 'руководство', 'начальство'],
        'деньги': ['финансы', 'средства', 'капитал', 'финансовые ресурсы'],
        'работа': ['труд', 'деятельность', 'занятость', 'трудовая деятельность'],
        'компания': ['фирма', 'организация', 'предприятие', 'корпорация'],
        'президент': ['глава государства', 'лидер', 'руководитель страны'],
        'закон': ['нормативный акт', 'постановление', 'правило', 'законодательство'],
        'суд': ['правосудие', 'судебная инстанция', 'судебный орган'],
        'выборы': ['голосование', 'избирательная кампания', 'электоральный процесс'],
        'теннис': ['большой теннис', 'игра в теннис', 'теннисный матч'],
        'матч': ['встреча', 'игра', 'поединок', 'соревнование'],
        'игрок': ['спортсмен', 'теннисист', 'участник', 'соперник'],
        'победа': ['выигрыш', 'успех', 'триумф', 'виктория'],
        'поражение': ['проигрыш', 'неудача', 'фиаско', 'провал']
    }
    
    # Разбиваем на предложения
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = []
    
    for sentence in sentences:
        words = sentence.split()
        new_words = []
        
        for word in words:
            word_lower = word.lower().strip('.,!?()"«»')
            if word_lower in synonyms and random.random() > 0.5:
                replacement = random.choice(synonyms[word_lower])
                # Сохраняем регистр
                if word[0].isupper():
                    replacement = replacement.capitalize()
                new_words.append(replacement)
            else:
                new_words.append(word)
        
        new_sentence = ' '.join(new_words)
        
        # Добавляем вводные конструкции в некоторые предложения
        if random.random() > 0.7 and len(result) < len(sentences) - 1:
            intros = [
                'По информации источников, ',
                'Как стало известно, ',
                'Согласно полученным данным, ',
                'По сообщениям очевидцев, ',
                'Как передает корреспондент, '
            ]
            intro = random.choice(intros)
            new_sentence = intro + new_sentence[0].lower() + new_sentence[1:]
        
        result.append(new_sentence)
    
    return ' '.join(result)

# ============ ФУНКЦИЯ ЗАГРУЗКИ ПОЛНОЙ СТАТЬИ ============
def fetch_full_article(url):
    """Загружает полный текст статьи"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем мусор
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        
        # Ищем основной контент
        content = None
        
        # Селекторы для разных сайтов
        selectors = [
            '.topic-body__content',
            '.b-topic__content',
            '.article__text',
            '.article-text',
            '.text-content',
            '.news-content',
            '.post-content',
            '.entry-content',
            'article',
            '[itemprop="articleBody"]',
            '.material-content',
            '.news-body'
        ]
        
        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        if content:
            # Получаем текст
            text = content.get_text()
            # Очищаем от лишних пробелов
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r' +', ' ', text)
            return text.strip()
        
        # Если не нашли по селекторам, собираем все параграфы
        paragraphs = soup.find_all('p')
        if paragraphs:
            text = '\n\n'.join([p.get_text() for p in paragraphs if len(p.get_text()) > 50])
            return text[:5000]  # Ограничиваем длину
        
        return None
        
    except Exception as e:
        print(f"      ⚠️ Ошибка загрузки: {e}")
        return None

# ============ ИНИЦИАЛИЗАЦИЯ FIREBASE ============
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    print("✅ Firebase загружен")
    
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase инициализирован")
    else:
        db = None
        print("⚠️ serviceAccountKey.json не найден")
except Exception as e:
    print(f"⚠️ Ошибка Firebase: {e}")
    db = None

# ============ RSS ИСТОЧНИКИ ============
RSS_FEEDS = {
    'Политика': ['https://lenta.ru/rss/news/politics', 'https://ria.ru/export/rss2/politics/index.xml'],
    'Экономика': ['https://lenta.ru/rss/news/economics', 'https://ria.ru/export/rss2/economy/index.xml'],
    'Технологии': ['https://lenta.ru/rss/news/technology', 'https://ria.ru/export/rss2/technology/index.xml'],
    'Авто': ['https://lenta.ru/rss/news/auto', 'https://motor.ru/rss'],
    'Киберспорт': ['https://www.cybersport.ru/rss'],
    'Культура': ['https://lenta.ru/rss/news/art', 'https://ria.ru/export/rss2/culture/index.xml'],
    'Спорт': ['https://lenta.ru/rss/news/sport', 'https://ria.ru/export/rss2/sport/index.xml']
}

def extract_images_from_entry(entry):
    """Извлечение картинок"""
    images = []
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                images.append(media['url'])
    return list(dict.fromkeys(images))

def fetch_and_save():
    print("\n=== НАЧАЛО СБОРА НОВОСТЕЙ ===")
    
json_path = 'public/news_data_v2.json'
    
    # Загружаем существующие ссылки
    existing_links = set()
    old_news = []
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                old_news = json.load(f)
                for item in old_news:
                    if item.get('originalLink'):
                        existing_links.add(item['originalLink'])
            print(f"✅ Загружено {len(old_news)} старых новостей")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки JSON: {e}")
    
    all_news = old_news.copy()
    new_count = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 Категория: {category}")
        
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                entries = feed.entries[:3]  # По 3 новости с каждой ленты
                
                for entry in entries:
                    if entry.link in existing_links:
                        continue
                    
                    print(f"  ✅ {entry.title[:60]}...")
                    
                    # Загружаем полный текст
                    full_text = fetch_full_article(entry.link)
                    
                    # Картинки
                    images = extract_images_from_entry(entry)
                    
                    # Описание из RSS
                    description = entry.get('summary', '')[:200]
                    if description:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(description, 'html.parser')
                        description = soup.get_text()[:200]
                    
                    # Формируем контент
                    if full_text:
                        # Перефразируем
                        rewritten = ai_rewrite_text(full_text)
                        # Разбиваем на абзацы
                        paragraphs = rewritten.split('\n\n')[:5]
                        content_html = ''.join([f'<p>{p.strip()}</p>\n' for p in paragraphs if p.strip()])
                        print(f"      📝 Текст: {len(content_html)} символов")
                    else:
                        content_html = f'<p>{description}</p>'
                        print(f"      ⚠️ Использую описание")
                    
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
                    
                    # Сохраняем в Firebase
                    if db:
                        try:
                            db.collection('news').add(news_item)
                        except:
                            pass
                    
                    time.sleep(1)
                    
            except Exception as e:
                print(f"  ⚠️ Ошибка: {feed_url}")
                continue
    
    # Сортируем и сохраняем
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    all_news = all_news[:200]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"✅ ИТОГИ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Добавлено новых: {new_count}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*50}")

if __name__ == '__main__':
    fetch_and_save()