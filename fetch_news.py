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
import random
from bs4 import BeautifulSoup

print("=== ЗАПУСК СКРИПТА С ПОЛНЫМ ТЕКСТОМ И ИИ ===")
print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ============ НАСТРОЙКИ ============
TIMEOUT = 15
MAX_ARTICLES_PER_FEED = 5  # Больше статей
REQUEST_DELAY = 3  # Задержка между запросами
MAX_IMAGES = 3

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
        'https://stopgame.ru/rss/news.xml',
        'https://www.cybersport.ru/rss'
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
USE_AI = True  # Включить ИИ

# OpenRouter (бесплатно) - получите ключ на https://openrouter.ai/
AI_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "gpt-3.5-turbo"  # Бесплатная модель
AI_API_KEY = "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"  # ЗАМЕНИТЕ НА ВАШ КЛЮЧ

# ИЛИ Google Gemini (бесплатно) - https://makersuite.google.com/
# AI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
# AI_MODEL = "gemini-pro"
# AI_API_KEY = "YOUR_GEMINI_KEY"

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
    
    # Удаляем специфичный мусор с сайтов
    garbage_patterns = [
        # Навигация
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
        
        # Спортивный мусор
        r'Мир Российская Премьер-лига',
        r'Фонбет Чемпионат КХЛ',
        r'Олимпиада Ставки',
        r'Футбол Бокс и ММА',
        r'Зимние виды Летние виды',
        r'Хоккей Автоспорт',
        r'ЗОЖ и фитнес',
        r'\d+\s*:\s*\d+\s*\d+-й тайм Live',
        r'\d+-й тур',
        r'Сегодня \d+:\d+',
        
        # Названия команд
        r'Оренбург|Зенит|Крылья Советов|Динамо Мх|Металлург Мг|Трактор|Лада|Спартак|Рубин|Краснодар|Торпедо|ХК Сочи|ЦСКА|Динамо М',
        
        # Реклама и соцсети
        r'Реклама.*?Реклама',
        r'Подпишись.*?новости',
        r'Соглашение.*?terms',
        r'ООО.*?Видео',
        r'VK.*?vkvideo\.ru',
        r'Telegram|Вконтакте|VK|YouTube|Instagram',
        r'12\+',
        r'18\+',
        
        # Общее
        r'Войти|Выйти|Регистрация',
        r'Эксклюзивы|Статьи|Галереи|Видео',
        r'Спецпроекты|Исследования|Мини-игры|Архив',
        r'Лента добра',
        r'Хочешь видеть только хорошие новости\?.*?Жми!',
        r'Вернуться в обычную ленту\?',
        r'Читайте также:.*?(?=\.|$)',
        r'Фото:.*?(?=\.|$)',
        r'Видео:.*?(?=\.|$)',
        r'©.*?\d{4}',
        r'Все права защищены',
        r'Источник:.*?(?=\.|$)',
        r'Ссылка:.*?(?=\.|$)',
        r'Поделиться|Скопировать ссылку',
        r'Комментарии|Обсудить',
    ]
    
    for pattern in garbage_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Убираем множественные точки и пробелы
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def extract_main_text(html_content, site_url):
    """Извлечение ПОЛНОГО текста статьи с сайта"""
    if not html_content:
        return None
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Удаляем все скрипты, стили, навигацию и рекламу
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
            tag.decompose()
        
        # Удаляем элементы с рекламой и навигацией по классам
        garbage_classes = [
            'ad', 'ads', 'advertisement', 'banner', 'promo', 'subscribe', 'newsletter',
            'menu', 'navigation', 'navbar', 'header', 'footer', 'sidebar', 'comments',
            'share', 'social', 'tags', 'related', 'recommendations', 'popular',
            'top-news', 'trending', 'cookie', 'popup', 'modal', 'overlay'
        ]
        
        for class_name in garbage_classes:
            for element in soup.find_all(class_=re.compile(class_name, re.I)):
                element.decompose()
        
        # СПОСОБ 1: Ищем статью по тегам
        article = None
        
        # Пробуем найти article
        article = soup.find('article')
        
        # Если нет article, ищем main
        if not article:
            article = soup.find('main')
        
        # Если нет main, ищем div с классом article или content
        if not article:
            article = soup.find('div', class_=re.compile(r'article|post|content|text|story|entry|news-body', re.I))
        
        # Если ничего не нашли, берем body
        if not article:
            article = soup.find('body')
        
        if not article:
            return None
        
        # Ищем все параграфы внутри статьи
        paragraphs = article.find_all('p')
        
        if not paragraphs:
            return None
        
        # Собираем текст из параграфов
        text_parts = []
        
        for p in paragraphs:
            # Получаем текст параграфа
            p_text = p.get_text(strip=True)
            
            # Проверяем, что это не мусор
            if len(p_text) < 30:  # Слишком короткие пропускаем
                continue
            
            # Проверяем на типичные мусорные фразы
            garbage_phrases = [
                'реклама', 'подпишись', 'подписаться', 'telegram', 'vk.com',
                'вконтакте', 'одноклассники', 'youtube', 'instagram', 'twitter',
                'facebook', 'следите за новостями', 'читайте также', 'по теме',
                'фото:', 'видео:', 'смотрите также', 'источник:', 'ссылка:',
                'поделиться', 'скопировать ссылку', 'комментарии', 'обсудить',
                'оставить комментарий', 'войдите', 'зарегистрируйтесь',
                'напишите нам', 'прислать новость', 'рекламодателям',
                'все права защищены', 'cookie', 'конфиденциальность',
                'наверх', 'показать полностью', 'читать далее'
            ]
            
            is_garbage = False
            for phrase in garbage_phrases:
                if phrase.lower() in p_text.lower():
                    is_garbage = True
                    break
            
            if not is_garbage:
                text_parts.append(p_text)
        
        # Если нашли достаточно параграфов, объединяем
        if len(text_parts) >= 3:
            full_text = ' '.join(text_parts)
            
            # Очищаем от лишних пробелов
            full_text = re.sub(r'\s+', ' ', full_text)
            
            # Убираем множественные точки
            full_text = re.sub(r'\.{2,}', '.', full_text)
            
            # Проверяем, что текст достаточно длинный
            if len(full_text) > 300:
                print(f"    ✅ Найдено {len(text_parts)} параграфов, {len(full_text)} символов")
                return full_text
        
        # СПОСОБ 2: Если параграфов мало, берем весь текст статьи
        article_text = article.get_text(separator=' ', strip=True)
        
        # Чистим от мусора
        article_text = re.sub(r'\s+', ' ', article_text)
        article_text = re.sub(r'\.{2,}', '.', article_text)
        
        # Удаляем типичные мусорные блоки
        sentences = article_text.split('. ')
        clean_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 40:  # Слишком короткие предложения
                continue
            
            # Проверяем на мусор
            is_garbage = False
            for phrase in garbage_phrases:
                if phrase.lower() in sentence.lower():
                    is_garbage = True
                    break
            
            if not is_garbage:
                clean_sentences.append(sentence)
        
        if len(clean_sentences) >= 3:
            return '. '.join(clean_sentences)
        
        # Если ничего не помогло, возвращаем очищенный текст
        return article_text[:3000]
        
    except Exception as e:
        print(f"  Ошибка парсинга HTML: {e}")
        return None

def fetch_article_text(url):
    """Загружает ПОЛНЫЙ текст статьи с очисткой"""
    try:
        print(f"    📥 Загрузка: {url[:60]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.google.com/',
        }
        
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        if response.status_code != 200:
            print(f"    ❌ Ошибка HTTP: {response.status_code}")
            return None
        
        # Пробуем определить кодировку
        if response.encoding and response.encoding.lower() != 'utf-8':
            try:
                response.encoding = 'utf-8'
            except:
                pass
        
        text = extract_main_text(response.text, url)
        
        if text and len(text) > 200:
            print(f"    ✅ Загружено {len(text)} символов")
            return text
        else:
            print(f"    ⚠️ Текст слишком короткий: {len(text) if text else 0} символов")
            return None
        
    except Exception as e:
        print(f"    ❌ Ошибка загрузки: {e}")
        return None

def ai_rewrite_text(text, title, category):
    """Перефразирование текста через ИИ для уникальности"""
    if not text or len(text) < 200:
        return text
    
    if not USE_AI:
        return text
    
    try:
        print(f"    🤖 ИИ обрабатывает текст...")
        
        # Промпт для ИИ
        prompt = f"""Перепиши эту новость своими словами, сохранив все важные факты и детали. 
Напиши полноценную статью из 3-5 абзацев. 
Убери лишнюю информацию, рекламу, ссылки. 
Сохрани стиль новостной статьи.

Категория: {category}
Заголовок: {title}

Текст новости:
{text}

Твоя переписанная статья (только текст статьи, без пояснений):"""

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Для OpenRouter
        data = {
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 800
        }
        
        response = requests.post(AI_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if "choices" in result:
                rewritten = result["choices"][0]["message"]["content"]
            else:
                rewritten = result.get("candidates", [{}])[0].get("content", "")
            
            # Очищаем результат
            rewritten = clean_text(rewritten)
            
            # Если получили нормальный текст, возвращаем
            if len(rewritten) > 200:
                print(f"    ✅ ИИ обработал, {len(rewritten)} символов")
                return rewritten
        
        print(f"    ⚠️ ИИ не сработал, используем оригинал")
        return text
        
    except Exception as e:
        print(f"    ❌ Ошибка ИИ: {e}")
        return text

def extract_images_from_entry(entry, full_html=None):
    """Извлечение картинок из новости"""
    images = []
    
    # Из media:content
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('url'):
                url = media['url']
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
    
    # Из media:thumbnail
    if hasattr(entry, 'media_thumbnail'):
        for thumb in entry.media_thumbnail:
            if thumb.get('url'):
                url = thumb['url']
                if url.startswith('//'):
                    url = 'https:' + url
                images.append(url)
    
    # Из summary
    summary = entry.get('summary', '') or entry.get('description', '')
    if summary:
        img_urls = re.findall(r'<img[^>]+src="([^">]+)"', summary)
        for url in img_urls:
            if url.startswith('//'):
                url = 'https:' + url
            images.append(url)
    
    # Из полного HTML, если есть
    if full_html:
        # Ищем все img теги
        img_urls = re.findall(r'<img[^>]+src="([^">]+)"', full_html)
        for url in img_urls:
            if url.startswith('//'):
                url = 'https:' + url
            # Пропускаем иконки и логотипы
            if not re.search(r'(icon|logo|avatar|favicon|pixel|spacer)', url.lower()):
                images.append(url)
    
    # Убираем дубликаты и фильтруем
    seen = set()
    unique = []
    
    for img in images:
        # Убираем параметры из URL
        base_url = img.split('?')[0]
        if base_url not in seen:
            # Проверяем, что это похоже на картинку
            if re.search(r'\.(jpg|jpeg|png|webp|gif|bmp)(\?|$)', base_url.lower()):
                seen.add(base_url)
                unique.append(img)
    
    return unique[:MAX_IMAGES]

def extract_description(entry):
    """Извлечение краткого описания"""
    # Пробуем разные поля
    description = (entry.get('summary', '') or 
                  entry.get('description', '') or 
                  entry.get('title', ''))
    
    # Очищаем
    description = re.sub(r'<[^>]+>', '', description)
    description = clean_text(description)
    
    # Берем первые 200 символов
    if len(description) > 200:
        description = description[:200] + '...'
    
    return description

def fetch_and_save():
    print(f"\n{'='*60}")
    print(f"  НАЧАЛО СБОРА НОВОСТЕЙ [{datetime.now()}]")
    print(f"{'='*60}")
    
    json_path = 'public/news_data_v3.json'
    version_path = 'public/version.json'
    
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
            print(f"📊 Загружено {len(old_news)} старых новостей")
        except:
            old_news = []
    
    all_news = old_news.copy()
    new_count = 0
    total_processed = 0
    failed = 0
    
    for category, feeds in RSS_FEEDS.items():
        print(f"\n📡 КАТЕГОРИЯ: {category}")
        
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                if not feed.entries:
                    print(f"  ⚠️ Нет записей: {feed_url.split('/')[-1]}")
                    continue
                
                print(f"  📰 RSS: {feed_url.split('/')[-1]} ({len(feed.entries)} записей)")
                
                for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                    total_processed += 1
                    
                    if entry.link in existing_links:
                        continue
                    
                    print(f"\n  🔍 НОВОСТЬ: {entry.title[:80]}...")
                    
                    # Загружаем полный текст
                    full_text = fetch_article_text(entry.link)
                    
                    if not full_text:
                        failed += 1
                        continue
                    
                    # Получаем описание
                    description = extract_description(entry)
                    
                    # Перефразируем текст через ИИ
                    if USE_AI and full_text:
                        rewritten = ai_rewrite_text(full_text, entry.title, category)
                        
                        # Разбиваем на абзацы
                        paragraphs = rewritten.split('\n\n')
                        content_html = ''
                        
                        for para in paragraphs[:5]:  # Максимум 5 абзацев
                            para = para.strip()
                            if para and len(para) > 30:
                                # Убираем лишние точки
                                para = re.sub(r'\.{2,}', '.', para)
                                content_html += f'<p>{para}</p>\n'
                    else:
                        # Если нет ИИ, просто используем очищенный текст
                        content_html = f'<p>{full_text[:500]}...</p>'
                    
                    # Получаем картинки
                    images = extract_images_from_entry(entry, full_text)
                    
                    # Создаём запись
                    news_item = {
                        'id': hashlib.md5(entry.link.encode()).hexdigest()[:16],
                        'title': entry.title[:200],
                        'description': description[:150] + '...' if len(description) > 150 else description,
                        'content': content_html,
                        'category': category,
                        'images': images,
                        'originalLink': entry.link,
                        'published': datetime.now().strftime('%H:%M, %d.%m.%Y'),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    all_news.append(news_item)
                    existing_links.add(entry.link)
                    new_count += 1
                    
                    print(f"    ✅ СОХРАНЕНО | Картинок: {len(images)} | Текст: {len(full_text)} символов")
                    
                    time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                print(f"  ❌ Ошибка RSS: {feed_url} - {e}")
                continue
    
    # Сортируем по дате (новые сверху)
    all_news.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Оставляем только последние 200
    if len(all_news) > 200:
        all_news = all_news[:200]
    
    # Сохраняем JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    
    # Сохраняем версию для сброса кэша
    version_data = {
        'version': datetime.now().timestamp(),
        'updated': datetime.now().isoformat(),
        'total': len(all_news),
        'new': new_count,
        'processed': total_processed,
        'failed': failed
    }
    
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ ИТОГИ РАБОТЫ:")
    print(f"   Всего новостей: {len(all_news)}")
    print(f"   Новых добавлено: {new_count}")
    print(f"   Всего обработано: {total_processed}")
    print(f"   Не удалось загрузить: {failed}")
    print(f"   С картинками: {sum(1 for item in all_news if item.get('images'))}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    fetch_and_save()