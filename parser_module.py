"""
Парсер расписания Музыкального училища имени Гнесиных (СПО).

Поддерживает все 10 отделений (включая Мастер по ремонту музыкальных инструментов).
Обрабатывает:
- Зеркальный и разряженный текст дней недели (н о п, к-т-в, адерс, гревтеч, .днп, .тп и т.д.)
- Специфические названия курсов (1 МПР, 2 МПР, 10 месяцев, 1 год 10 месяцев)
- Корректное распознавание общепоточных лекций (не привязывая их ошибочно к гр. А)
- Объединение подгрупп (А, Б, В, Г) под единым курсом с метками (гр. А, гр. Б)
- Фильтрацию нерасписанных строк (списки студентов)
"""

import os
import re
import time
import datetime
import logging
import requests
from bs4 import BeautifulSoup
import pdfplumber

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, 'cache')
SCHEDULE_URL = 'https://www.gnesin.ru/studentam/schedule'
BASE_URL = 'https://www.gnesin.ru'
CACHE_EXPIRY = 24 * 3600

# Отделения СПО
DEPARTMENTS = {
    '01': ('01_piano',  'Фортепиано и орган'),
    '02': ('02_str',    'Оркестровые струнные инструменты'),
    '03': ('03_wind',   'Духовые и ударные инструменты'),
    '04': ('04_oni',    'Инструменты народного оркестра'),
    '05': ('05_voc',    'Вокальное искусство'),
    '06': ('06_snp',    'Сольное народное пение'),
    '07': ('07_rnh',    'Хоровое народное пение'),
    '08': ('08_dho',    'Хоровое дирижирование'),
    '09': ('09_teor',   'Теория музыки'),
    '10': ('10_master', 'Мастер по ремонту инструментов'),
}

DAYS_ORDER = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

# Распознавание всех вариантов дней недели (в т.ч. зеркальных и сокращенных)
MIRROR_DAYS = {
    'понедельник': 'Понедельник',
    'ньледеноп':   'Понедельник',
    'киньледеноп': 'Понедельник',
    'ноп':         'Понедельник',
    'деноп':       'Понедельник',
    'денопп':      'Понедельник',
    'днп':         'Понедельник',
    'кноп':        'Понедельник',
    'к-ноп':       'Понедельник',

    'вторник':     'Вторник',
    'кинротв':     'Вторник',
    'ктв':         'Вторник',
    'тв':          'Вторник',
    'к-тв':        'Вторник',

    'среда':       'Среда',
    'адерс':       'Среда',
    'рс':          'Среда',

    'четверг':     'Четверг',
    'гревтеч':     'Четверг',
    'втеч':        'Четверг',
    'втч':         'Четверг',

    'пятница':     'Пятница',
    'ацинтяп':     'Пятница',
    'нтяп':        'Пятница',
    'тп':          'Пятница',

    'суббота':     'Суббота',
    'атоббус':     'Суббота',
    'ббус':        'Суббота',
    'бус':         'Суббота',
    'бс':          'Суббота',

    'воскресенье': 'Воскресенье',
    'еьнесеркосов':'Воскресенье',
}

os.makedirs(CACHE_DIR, exist_ok=True)


# ═══════════════════════════════════════════
#   Скачивание и кэширование
# ═══════════════════════════════════════════

def _scrape_pdf_links() -> dict:
    links = {}
    try:
        resp = requests.get(SCHEDULE_URL, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '.pdf' in href and '/schedule/' in href:
                url = href if href.startswith('http') else BASE_URL + href
                fname = url.split('/')[-1]
                for prefix, _ in DEPARTMENTS.values():
                    if fname.startswith(prefix):
                        links[prefix] = url
    except Exception as e:
        logger.error(f"Ошибка скрейпинга: {e}")
    return links


def _cache_path(prefix: str) -> str:
    return os.path.join(CACHE_DIR, f"{prefix}.pdf")


def _is_fresh(path: str) -> bool:
    return os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CACHE_EXPIRY


def _download(url: str, path: str) -> bool:
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        logger.info(f"Скачан: {path}")
        return True
    except Exception as e:
        logger.error(f"Ошибка скачивания {url}: {e}")
        return False


def _ensure_pdf(dept_id: str) -> str | None:
    info = DEPARTMENTS.get(dept_id)
    if not info:
        return None
    prefix = info[0]
    path = _cache_path(prefix)
    if _is_fresh(path):
        return path
    links = _scrape_pdf_links()
    url = links.get(prefix)
    if url and _download(url, path):
        return path
    return path if os.path.exists(path) else None


# ═══════════════════════════════════════════
#   Парсинг PDF
# ═══════════════════════════════════════════

def _detect_day(cell: str | None) -> str | None:
    if not cell:
        return None
    clean = cell.strip().lower().replace(' ', '').replace('\n', '').replace('-', '').strip('.')
    for k, v in MIRROR_DAYS.items():
        k_clean = k.replace('-', '')
        if clean == k_clean or (len(clean) >= 2 and (clean in k_clean or k_clean in clean)):
            return v
    return None


def _clean_time(time_str: str | None) -> str:
    if not time_str:
        return ''
    m = re.search(r'(\d{1,2})[.:,](\d{2})\s*[-–—]\s*(\d{1,2})[.:,](\d{2})', time_str)
    if m:
        return f"{int(m.group(1))}:{m.group(2)}–{int(m.group(3))}:{m.group(4)}"
    return ''


def _find_all_times(time_str: str | None) -> list[str]:
    if not time_str:
        return []
    matches = re.findall(r'(\d{1,2})[.:,](\d{2})\s*[-–—]\s*(\d{1,2})[.:,](\d{2})', time_str)
    return [f"{int(m[0])}:{m[1]}–{int(m[2])}:{m[3]}" for m in matches]


def _is_noise_row(row_cells: list) -> bool:
    for c in row_cells:
        if not c:
            continue
        s = str(c).lower().replace(' ', '')
        if any(w in s for w in ['списки', 'маппург', 'погруппам', 'списокпо']):
            return True
        if re.search(r'^\s*1\.\s*2\.\s*3\.', str(c).strip()):
            return True
    return False


def _detect_course(text: str, page_num: int = 1) -> str:
    """Определяет номер курса с учётом отделений."""
    if '10 месяцев' in text and '1 год' not in text:
        return '1 курс (10 мес.)'
    if '1 год 10 месяцев' in text or '1 год 10 мес' in text:
        return '1 курс (1 год 10 мес.)'
    if '2 МПР' in text or '2МПР' in text:
        return '2 курс'
    if '1 МПР' in text or '1МПР' in text:
        return '1 курс'

    m = re.search(r'(\d)\s*курс', text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} курс"

    roman = {'I': '1', 'II': '2', 'III': '3', 'IV': '4'}
    m = re.search(r'(I{1,3}V?|IV)\s*курс', text, re.IGNORECASE)
    if m:
        num = roman.get(m.group(1).upper(), m.group(1))
        return f"{num} курс"

    return f"{page_num} курс"


def _parse_cell(cell_str: str | None, group_code: str, is_course_wide: bool) -> dict | None:
    if not cell_str or not cell_str.strip() or cell_str.strip() == '—':
        return None

    lines = [l.strip() for l in cell_str.strip().split('\n') if l.strip()]
    if not lines:
        return None

    subject = lines[0]
    result = {'subject': subject, 'teacher': '', 'room': ''}

    # Если предмет относится только к конкретной подгруппе и еще не имеет метки
    if not is_course_wide and not re.search(r'\(|\bгр\.|\bгруппа\b', subject, re.IGNORECASE):
        result['subject'] = f"{subject} (гр. {group_code})"

    if len(lines) > 1:
        rest = lines[1]
        room_match = re.search(r'(?:кл|Кл|ауд|каб)\.?\s*(\S+)', rest)
        if room_match:
            result['room'] = room_match.group(1).strip('.,')
            result['teacher'] = rest[:room_match.start()].strip().rstrip(',.')
        else:
            result['teacher'] = rest

    for extra_line in lines[2:]:
        room_match = re.search(r'(?:кл|Кл|ауд|каб)\.?\s*(\S+)', extra_line)
        if room_match and not result['room']:
            result['room'] = room_match.group(1).strip('.,')
        elif not result['teacher']:
            result['teacher'] = extra_line.strip()

    return result if result['subject'] else None


def _parse_pdf(pdf_path: str) -> tuple[list[str], dict]:
    all_courses = []
    all_schedule = {}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ''
                course = _detect_course(text, page_num)
                if course not in all_courses:
                    all_courses.append(course)
                if course not in all_schedule:
                    all_schedule[course] = {day: [] for day in DAYS_ORDER}

                tables = page.find_tables()
                if not tables:
                    continue

                t = tables[0]
                raw_data = t.extract()
                if not raw_data or len(raw_data) < 2:
                    continue

                # Проверка дня недели в первой ячейке шапки
                header_day = _detect_day(raw_data[0][0])
                current_day = header_day

                # Подгруппы из шапки (колонки со 2-го индекса)
                header_row = raw_data[0]
                col_groups = {}
                for ci, cell in enumerate(header_row[2:], 2):
                    g_code = (cell or '').strip().replace('группа ', '').replace('группа', '').replace('Группа ', '').replace('Группа', '').strip()
                    if not g_code:
                        g_code = chr(ord('А') + ci - 2)
                    col_groups[ci] = g_code

                header_cells = t.rows[0].cells
                right_boundary = max((c[2] for c in header_cells if c), default=500)
                left_group_x = min((c[0] for c in header_cells[2:] if c), default=130)
                full_group_width = right_boundary - left_group_x
                multi_col = len(col_groups) > 1

                # Границы каждой колонки
                col_bounds = {}
                for ci in col_groups:
                    c = header_cells[ci] if ci < len(header_cells) else None
                    if c:
                        col_bounds[ci] = (c[0], c[2])

                pending_times = []

                for r_idx in range(1, len(raw_data)):
                    row_data = raw_data[r_idx]
                    row_obj = t.rows[r_idx]
                    if _is_noise_row(row_data):
                        continue

                    day = _detect_day(row_data[0])
                    if day:
                        current_day = day
                        pending_times = []

                    if not current_day or current_day not in all_schedule[course]:
                        continue

                    # Извлечение времени
                    time_cell = row_data[1] if len(row_data) > 1 else ''
                    all_t = _find_all_times(time_cell)
                    if len(all_t) > 1:
                        time_str = all_t[0]
                        pending_times = all_t[1:]
                    elif len(all_t) == 1:
                        time_str = all_t[0]
                    elif pending_times:
                        time_str = pending_times.pop(0)
                    else:
                        time_str = _clean_time(time_cell)

                    for ci, g_code in col_groups.items():
                        if ci >= len(row_data) or not row_data[ci] or not row_data[ci].strip() or row_data[ci].strip() == '—':
                            continue

                        cell_obj = row_obj.cells[ci] if ci < len(row_obj.cells) else None
                        is_course_wide = False
                        effective_g_code = g_code

                        if cell_obj and multi_col:
                            w = cell_obj[2] - cell_obj[0]
                            if w >= 0.70 * full_group_width:
                                # Проверяем координаты слов внутри ячейки
                                words = page.crop(cell_obj).extract_words()
                                cw_words = [w_obj for w_obj in words if w_obj['x0'] >= left_group_x]
                                if cw_words:
                                    min_x = min(w_obj['x0'] for w_obj in cw_words)
                                    max_x = max(w_obj['x1'] for w_obj in cw_words)
                                    matched_cols = [c_idx for c_idx, (bx0, bx1) in col_bounds.items() if not (max_x < bx0 or min_x > bx1)]
                                    if len(matched_cols) == 1:
                                        effective_g_code = col_groups[matched_cols[0]]
                                        is_course_wide = False
                                    else:
                                        is_course_wide = True
                                else:
                                    is_course_wide = True
                        elif not multi_col:
                            is_course_wide = True

                        lesson = _parse_cell(row_data[ci], effective_g_code, is_course_wide)
                        if lesson:
                            lesson['time'] = time_str if time_str else 'Время уточняется'
                            all_schedule[course][current_day].append(lesson)

    except Exception as e:
        logger.error(f"Ошибка парсинга PDF {pdf_path}: {e}")
        return ['1 курс'], {}

    if not all_courses:
        all_courses = ['1 курс']

    return all_courses, all_schedule


# ═══════════════════════════════════════════
#   Публичный API
# ═══════════════════════════════════════════

def get_department_list() -> list[tuple[str, str]]:
    return [(k, v[1]) for k, v in DEPARTMENTS.items()]


def get_dept_name(dept_id: str) -> str:
    info = DEPARTMENTS.get(dept_id)
    return info[1] if info else 'Неизвестное отделение'


def get_available_groups(dept_id: str) -> list[str]:
    pdf_path = _ensure_pdf(dept_id)
    if not pdf_path:
        return ['1 курс']
    courses, _ = _parse_pdf(pdf_path)
    return courses


def get_schedule_data(dept_id: str) -> dict:
    pdf_path = _ensure_pdf(dept_id)
    if not pdf_path:
        return {}
    _, schedule = _parse_pdf(pdf_path)
    return schedule


def update_cache():
    logger.info("Обновление кэша...")
    links = _scrape_pdf_links()
    for dept_id, (prefix, name) in DEPARTMENTS.items():
        url = links.get(prefix)
        if url:
            _download(url, _cache_path(prefix))
    ts_path = os.path.join(CACHE_DIR, 'last_update.txt')
    with open(ts_path, 'w') as f:
        f.write(str(time.time()))
    logger.info("Кэш обновлён")


def get_last_update_time() -> str:
    ts_path = os.path.join(CACHE_DIR, 'last_update.txt')
    if os.path.exists(ts_path):
        try:
            ts = float(open(ts_path).read().strip())
            return datetime.datetime.fromtimestamp(ts).strftime('%d.%m.%Y %H:%M')
        except Exception:
            pass
    newest = 0
    for f in os.listdir(CACHE_DIR):
        if f.endswith('.pdf'):
            mt = os.path.getmtime(os.path.join(CACHE_DIR, f))
            if mt > newest:
                newest = mt
    if newest:
        return datetime.datetime.fromtimestamp(newest).strftime('%d.%m.%Y %H:%M')
    return 'Никогда'
