#!/usr/bin/env python3
import json
import os
from datetime import datetime

# Конфигурация
SITE_URL = "https://tolk-news.ru"
NEWS_FILE = "public/news_data_v3.json"
SITEMAP_FILE = "public/sitemap.xml"

def generate_sitemap():
    print("Генерация sitemap.xml...")

    # Читаем все новости
    if not os.path.exists(NEWS_FILE):
        print("Файл с новостями не найден, создаю базовую карту.")
        news_items = []
    else:
        with open(NEWS_FILE, 'r', encoding='utf-8') as f:
            news_items = json.load(f)

    # Начало XML
    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <!-- Главная страница -->
  <url>
    <loc>''' + SITE_URL + '''/</loc>
    <lastmod>''' + datetime.now().strftime('%Y-%m-%d') + '''</lastmod>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
'''
    # Добавляем категории
    categories = ['Политика', 'Экономика', 'Технологии', 'Авто', 'Киберспорт', 'Культура', 'Спорт']
    for cat in categories:
        xml_content += f'''  <url>
    <loc>{SITE_URL}/?cat={cat}</loc>
    <lastmod>{datetime.now().strftime('%Y-%m-%d')}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>0.9</priority>
  </url>
'''

    # Добавляем все статьи из JSON
    for item in news_items:
        # Берем дату из timestamp новости
        try:
            date_obj = datetime.fromisoformat(item['timestamp'])
            lastmod = date_obj.strftime('%Y-%m-%d')
        except:
            lastmod = datetime.now().strftime('%Y-%m-%d')

        xml_content += f'''  <url>
    <loc>{SITE_URL}/article.html?id={item['id']}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
'''

    # Закрываем тег
    xml_content += '</urlset>'

    # Записываем файл
    with open(SITEMAP_FILE, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    print(f"✅ Sitemap успешно сгенерирован. Добавлено статей: {len(news_items)}")

if __name__ == "__main__":
    generate_sitemap()