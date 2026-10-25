#!/usr/bin/env python3
"""
Скрипт генерации красивых PNG-изображений расписания в тёплых светлых тонах Mini App:
- Фон: тёплый кремовый (#FAF8F5)
- Карточки: белые (#FFFFFF) с мягкой рамкой (#E8E5DF) и янтарной полосой слева (#F59E0B)
- Бейджи: янтарные (#FEF3C7, #FDE68A, текст #92400E)
- Правильные названия учебных заведений (Училище / Академия)
- Динамическая высота (никаких обрезанных пар!)
- Генерация как общих фото на неделю, так и отдельных вертикальных фото на каждый день недели (1..6)
"""

import os
import json
import re
import time
from PIL import Image, ImageDraw, ImageFont

DAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

LEVEL_TITLES = {
    'spo': 'Музыкальное училище имени Гнесиных (СПО)',
    'bachelor': 'Российская академия музыки имени Гнесиных (Бакалавриат)',
    'specialist': 'Российская академия музыки имени Гнесиных (Специалитет)',
    'master': 'Российская академия музыки имени Гнесиных (Магистратура)',
    'assistantship': 'Российская академия музыки имени Гнесиных (Ассистентура-стажировка)',
    'postgraduate': 'Российская академия музыки имени Гнесиных (Аспирантура)',
}

def to_slug(s: str) -> str:
    t = s.lower().replace('курс', 'kurs').replace('мес', 'mes').replace('кл', 'kl')
    return re.sub(r'[^a-z0-9_-]', '_', t).strip('_')

def wrap_text(text: str, max_chars: int = 24) -> list[str]:
    """Переносит длинный текст по словам на 2 строки."""
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    lines = []
    current = []
    for w in words:
        if len(' '.join(current + [w])) <= max_chars:
            current.append(w)
        else:
            if current:
                lines.append(' '.join(current))
                current = [w]
            else:
                lines.append(w)
            if len(lines) >= 2:
                break
    if current and len(lines) < 2:
        lines.append(' '.join(current))
    elif current and len(lines) >= 2:
        lines[1] += '…'
    return lines

def render_day_image(dept_name, course_name, school_title, day_name, lessons, filename,
                     font_title_day, font_sub_day, font_group_day, font_badge_day,
                     font_subject_day, font_meta_day, font_empty_day):
    WIDTH = 800
    start_y = 175
    card_gap = 14

    if not lessons:
        HEIGHT = 440
        card_heights = []
    else:
        card_heights = []
        total_cards_h = 0
        for l in lessons:
            sub = l.get('subject', '')
            ch = 135 if len(sub) <= 45 else 160
            card_heights.append(ch)
            total_cards_h += ch + card_gap
        HEIGHT = max(500, start_y + total_cards_h + 35)

    img = Image.new('RGB', (WIDTH, HEIGHT), color='#FAF8F5')
    draw = ImageDraw.Draw(img)

    # Шапка
    draw.text((50, 30), day_name.upper(), fill='#202421', font=font_title_day)
    draw.text((50, 72), school_title, fill='#666E64', font=font_sub_day)

    # Бейдж направления
    badge_txt = f'{dept_name} • {course_name}'
    bw = font_group_day.getlength(badge_txt)
    draw.rounded_rectangle([(50, 108), (50 + bw + 26, 144)], radius=8, fill='#FEF3C7', outline='#FCD34D', width=1)
    draw.text((63, 114), badge_txt, fill='#92400E', font=font_group_day)
    draw.line([(50, 158), (WIDTH - 50, 158)], fill='#E8E5DF', width=2)

    card_y = start_y
    if not lessons:
        draw.rounded_rectangle([(50, card_y), (WIDTH - 50, card_y + 90)], radius=12, fill='#FFFFFF', outline='#E8E5DF', width=1)
        draw.text((WIDTH // 2, card_y + 32), 'Занятий нет 🎉', fill='#9CA3AF', font=font_empty_day, anchor='mt')
    else:
        for i, (l, ch) in enumerate(zip(lessons, card_heights)):
            draw.rounded_rectangle([(50, card_y), (WIDTH - 50, card_y + ch)], radius=12, fill='#FFFFFF', outline='#E8E5DF', width=1)
            draw.rounded_rectangle([(50, card_y + 10), (55, card_y + ch - 10)], radius=2, fill='#F59E0B')

            t_text = l.get('time', 'Время уточняется')
            b_txt = f'{t_text} • {i+1} пара'
            tbw = font_badge_day.getlength(b_txt)
            draw.rounded_rectangle([(70, card_y + 12), (70 + tbw + 18, card_y + 36)], radius=6, fill='#FEF3C7', outline='#FDE68A', width=1)
            draw.text((79, card_y + 14), b_txt, fill='#92400E', font=font_badge_day)

            sub = l.get('subject', '')
            if len(sub) <= 45:
                draw.text((70, card_y + 46), sub, fill='#202421', font=font_subject_day)
                line_y = card_y + 76
            else:
                words = sub.split()
                line1, line2 = '', ''
                for w in words:
                    if len(line1 + ' ' + w) <= 42 and not line2:
                        line1 += (' ' + w) if line1 else w
                    else:
                        line2 += (' ' + w) if line2 else w
                draw.text((70, card_y + 44), line1, fill='#202421', font=font_subject_day)
                draw.text((70, card_y + 68), line2[:45], fill='#202421', font=font_subject_day)
                line_y = card_y + 98

            teach = l.get('teacher', '')
            if teach:
                draw.text((70, line_y), f'👤 {teach[:40]}', fill='#666E64', font=font_meta_day)
                line_y += 24
            rm = l.get('room', '')
            if rm:
                draw.text((70, line_y), f'🏫 Ауд. {rm}', fill='#4A5734', font=font_meta_day)

            card_y += ch + card_gap

    img.save(filename, quality=90)


def main():
    t0 = time.time()
    os.makedirs('public/schedules', exist_ok=True)

    with open('public/data/schedules.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Шрифты для недели
    font_title = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 34)
    font_sub = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Regular.ttf', 18)
    font_group = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 19)
    font_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 20)
    font_badge = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 14)
    font_subject = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 15)
    font_meta = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Regular.ttf', 13)
    font_empty = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Italic.ttf', 16)

    # Шрифты для отдельных дней
    font_title_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 30)
    font_sub_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Regular.ttf', 18)
    font_group_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 19)
    font_badge_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 15)
    font_subject_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Bold.ttf', 19)
    font_meta_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Regular.ttf', 16)
    font_empty_day = ImageFont.truetype('/usr/share/fonts/liberation/LiberationSans-Italic.ttf', 18)

    manifest = {}
    count_week = 0
    count_days = 0

    for dept_id, dept_info in data.items():
        dept_name = dept_info.get('dept_name', 'Отделение')
        level = dept_info.get('level', 'spo')
        school_title = LEVEL_TITLES.get(level, 'Музыкальное училище имени Гнесиных')
        schedule = dept_info.get('schedule', {})
        manifest[dept_id] = {}

        for course_name, days_data in schedule.items():
            slug = to_slug(course_name)
            filename_week = f'{dept_id}_{slug}.png'

            manifest[dept_id][course_name] = {
                'week': filename_week,
                'days': {}
            }

            # ══════════════════════════════════════════════════════
            # 1. ГЕНЕРАЦИЯ ОБЩЕЙ КАРТИНКИ НА НЕДЕЛЮ (6 колонок)
            # ══════════════════════════════════════════════════════
            max_lessons_count = max((len(days_data.get(d, [])) for d in DAYS), default=0)
            WIDTH = 1920
            card_slot_h = 145
            HEIGHT = max(1080, 200 + max_lessons_count * card_slot_h + 50)

            img_week = Image.new('RGB', (WIDTH, HEIGHT), color='#FAF8F5')
            draw_week = ImageDraw.Draw(img_week)

            # Шапка
            draw_week.text((60, 34), 'РАСПИСАНИЕ НА НЕДЕЛЮ', fill='#202421', font=font_title)
            draw_week.text((60, 80), school_title, fill='#666E64', font=font_sub)

            # Янтарный бейдж группы
            label_text = f'{dept_name} • {course_name}'
            label_w = font_group.getlength(label_text)
            draw_week.rounded_rectangle(
                [(60, 114), (60 + label_w + 26, 148)],
                radius=8,
                fill='#FEF3C7',
                outline='#FCD34D',
                width=1
            )
            draw_week.text((73, 120), label_text, fill='#92400E', font=font_group)

            # Разделительная полоса
            draw_week.line([(60, 164), (WIDTH - 60, 164)], fill='#E8E5DF', width=2)

            cols = len(DAYS)
            padding_x = 60
            col_gap = 18
            avail_w = WIDTH - (2 * padding_x) - ((cols - 1) * col_gap)
            col_w = avail_w // cols
            start_y = 182

            for i, day in enumerate(DAYS):
                col_x = padding_x + i * (col_w + col_gap)

                # Шапка дня недели
                draw_week.rounded_rectangle(
                    [(col_x, start_y), (col_x + col_w, start_y + 36)],
                    radius=8,
                    fill='#FFFFFF',
                    outline='#E8E5DF',
                    width=1
                )
                draw_week.rounded_rectangle(
                    [(col_x + 16, start_y + 32), (col_x + col_w - 16, start_y + 35)],
                    radius=2,
                    fill='#F59E0B'
                )
                draw_week.text((col_x + col_w // 2, start_y + 7), day.upper(), fill='#202421', font=font_day, anchor='mt')

                lessons = days_data.get(day, [])
                card_y = start_y + 46

                if not lessons:
                    draw_week.rounded_rectangle(
                        [(col_x, card_y), (col_x + col_w, card_y + 70)],
                        radius=10,
                        fill='#FFFFFF',
                        outline='#E8E5DF',
                        width=1
                    )
                    draw_week.text(
                        (col_x + col_w // 2, card_y + 24),
                        'Занятий нет 🎉',
                        fill='#9CA3AF',
                        font=font_empty,
                        anchor='mt'
                    )
                else:
                    for l_idx, lesson in enumerate(lessons):
                        sub_text = lesson.get('subject', '')
                        sub_lines = wrap_text(sub_text, max_chars=24)
                        card_h = 136 if len(sub_lines) > 1 else 118

                        draw_week.rounded_rectangle(
                            [(col_x, card_y), (col_x + col_w, card_y + card_h)],
                            radius=12,
                            fill='#FFFFFF',
                            outline='#E8E5DF',
                            width=1
                        )
                        draw_week.rounded_rectangle(
                            [(col_x, card_y + 8), (col_x + 4, card_y + card_h - 8)],
                            radius=2,
                            fill='#F59E0B'
                        )

                        time_text = lesson.get('time', '')
                        badge_text = f'{time_text} • {l_idx+1} пара' if time_text else f'{l_idx+1} пара'
                        draw_week.rounded_rectangle(
                            [(col_x + 12, card_y + 8), (col_x + col_w - 12, card_y + 28)],
                            radius=5,
                            fill='#FEF3C7',
                            outline='#FDE68A',
                            width=1
                        )
                        draw_week.text((col_x + 18, card_y + 10), badge_text, fill='#92400E', font=font_badge)

                        line_y = card_y + 35
                        for s_line in sub_lines:
                            draw_week.text((col_x + 12, line_y), s_line, fill='#202421', font=font_subject)
                            line_y += 19

                        teacher = lesson.get('teacher', '')
                        if teacher:
                            if len(teacher) > 28:
                                teacher = teacher[:26] + '…'
                            draw_week.text((col_x + 12, line_y + 3), f'👤 {teacher}', fill='#666E64', font=font_meta)
                            line_y += 18

                        room = lesson.get('room', '')
                        if room:
                            draw_week.text((col_x + 12, line_y + 2), f'🏫 Ауд. {room}', fill='#4A5734', font=font_meta)

                        card_y += card_h + 10

            img_week.save(f'public/schedules/{filename_week}', quality=92)
            count_week += 1

            # ══════════════════════════════════════════════════════
            # 2. ГЕНЕРАЦИЯ ОТДЕЛЬНЫХ ФОТО НА КАЖДЫЙ ДЕНЬ (1..6) ДЛЯ СПО (Училище)
            # ══════════════════════════════════════════════════════
            is_spo = dept_id.isdigit() and 1 <= int(dept_id) <= 10
            if is_spo:
                for day_idx, day_name in enumerate(DAYS, 1):
                    day_filename = f'{dept_id}_{slug}_d{day_idx}.png'
                    day_lessons = days_data.get(day_name, [])
                    render_day_image(
                        dept_name, course_name, school_title, day_name, day_lessons,
                        f'public/schedules/{day_filename}',
                        font_title_day, font_sub_day, font_group_day, font_badge_day,
                        font_subject_day, font_meta_day, font_empty_day
                    )
                    manifest[dept_id][course_name]['days'][str(day_idx)] = day_filename
                    count_days += 1

    with open('tgcloud/lib/image_manifest.js', 'w', encoding='utf-8') as f:
        f.write('export const scheduleImages = ' + json.dumps(manifest, ensure_ascii=False, indent=2) + ';\n')

    print(f'✅ Успешно сгенерировано {count_week} картинок на неделю и {count_days} картинок по дням за {time.time() - t0:.2f} сек!')

if __name__ == '__main__':
    main()
