#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

print("=== ТЕСТОВЫЙ СКРИПТ ===")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in current dir: {os.listdir('.')}")
print("=======================")

print("✅ Скрипт успешно запущен")
sys.exit(0)