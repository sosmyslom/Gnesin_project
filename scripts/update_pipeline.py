#!/usr/bin/env python3
"""
Единый конвейер автоматического обновления расписания Гнесинки.
1. Скачивает и парсит расписание СПО (Училище) и Академии (Бакалавриат, Специалитет, Магистратура).
2. Сравнивает полученные данные с текущими в public/data/schedules.json.
3. Если есть изменения:
   - Обновляет public/data/schedules.json и tgcloud/lib/default_schedule.js
   - Перегенерирует картинки расписания (generate_images.py)
   - Деплоит обновления в облако через npx @tgcloud/cli push
"""

import os
import sys
import json
import time
import subprocess
import hashlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULES_FILE = os.path.join(BASE_DIR, 'public', 'data', 'schedules.json')

def get_file_hash(filepath):
    if not os.path.exists(filepath):
        return ''
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def run_cmd(cmd, cwd=BASE_DIR):
    print(f"▶ Запуск: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"⚠️ Ошибка выполнения команды: {res.stderr}")
        return False, res.stderr
    return True, res.stdout

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Запуск проверки обновления расписания...")

    old_hash = get_file_hash(SCHEDULES_FILE)

    venv_python = os.path.join(BASE_DIR, 'venv', 'bin', 'python')
    python_bin = venv_python if os.path.exists(venv_python) else sys.executable

    # 1. Запуск парсеров
    print("1️⃣ Парсинг актуальных данных с сайтов...")
    # Парсер СПО
    ok, out = run_cmd([python_bin, 'parser_module.py'])
    if not ok:
        print("Ошибка парсинга СПО, продолжаем с имеющимися данными.")

    # 2. Проверка изменений в schedules.json
    new_hash = get_file_hash(SCHEDULES_FILE)
    force = '--force' in sys.argv

    if old_hash == new_hash and not force:
        print("✅ Расписание актуально, изменений на сайтах нет. Обновление не требуется.")
        return

    print("🔄 Обнаружены изменения в расписании!")

    # 3. Генерация картинок
    print("2️⃣ Генерация новых картинок расписания...")
    ok, out = run_cmd([python_bin, 'generate_images.py'])
    if not ok:
        print(f"Ошибка генерации картинок: {out}")
        return

    # 4. Деплой в tgcloud
    print("3️⃣ Развертывание обновлений в облако tgcloud...")
    ok, out = run_cmd(['npm', 'run', 'deploy'])
    if not ok:
        print(f"Ошибка деплоя: {out}")
        return

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🎉 Расписание успешно обновлено и задеплоено в боте!")

if __name__ == '__main__':
    main()
