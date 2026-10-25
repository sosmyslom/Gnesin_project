"""
Модуль форматирования расписания для Telegram.
Красивый вывод с эмодзи, номерами пар, четкими разделителями дней.
"""

import datetime

DAYS_RU = [
    'Понедельник', 'Вторник', 'Среда',
    'Четверг', 'Пятница', 'Суббота', 'Воскресенье',
]

MONTHS_RU = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

DAY_DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def _date_label(dt: datetime.date) -> str:
    """Формирует строку вида 'Понедельник, 29 сентября'."""
    return f"{DAYS_RU[dt.weekday()]}, {dt.day} {MONTHS_RU[dt.month - 1]}"


def _lesson_block(lesson: dict, num: int) -> str:
    """Форматирует одну парную дисциплину."""
    lines = [f"<b>{num} пара:</b>"]

    if lesson.get('subject'):
        lines.append(f"📚 <b>{lesson['subject']}</b>")
    if lesson.get('time'):
        lines.append(f"🕐 <i>{lesson['time']}</i>")
    elif lesson.get('time_start'):
        t = lesson['time_start']
        if lesson.get('time_end'):
            t += f"–{lesson['time_end']}"
        lines.append(f"🕐 <i>{t}</i>")

    teacher = (lesson.get('teacher') or '').strip()
    room = (lesson.get('room') or '').strip()
    if teacher and not room:
        import re
        m_room = re.search(r'(?:кл\.|ауд\.|каб\.|[Кк]\.)\s*([0-9a-zA-Zа-яА-ЯёЁ\-_\./]+(?:\s*\([^\)]+\))?)', teacher)
        if m_room:
            room = m_room.group(0).strip()
            teacher = teacher[:m_room.start()].strip(' ,.-/')
    if room:
        import re
        room = re.sub(r'^[Кк]\.\s*', '', room)

    if teacher:
        lines.append(f"👤 {teacher}")
    if room:
        lines.append(f"🏫 Аудитория: <b>{room}</b>")

    return "\n".join(lines)


def _personal_block(lesson: dict) -> str:
    """Форматирует личный урок по специальности."""
    lines = [f"🎵 <b>{lesson['subject']}</b> (<i>личный урок</i>)"]

    t = lesson['time_start']
    if lesson.get('time_end'):
        t += f"–{lesson['time_end']}"
    lines.append(f"🕐 <i>{t}</i>")
    if lesson.get('teacher'):
        lines.append(f"👤 {lesson['teacher']}")
    if lesson.get('room'):
        lines.append(f"🏫 Аудитория: <b>{lesson['room']}</b>")

    return "\n".join(lines)


def _render_day(day_data, dt: datetime.date, personal: list = None, show_divider: bool = True) -> str:
    """
    Рендерит расписание одного дня с выразительным заголовком и разделителем.
    """
    parts = []
    if show_divider:
        parts.append(DAY_DIVIDER)
    parts.append(f"📅 <b>{_date_label(dt)}</b>")
    parts.append("")

    has_group_lessons = False

    # Групповые пары
    if isinstance(day_data, list) and day_data:
        has_group_lessons = True
        for i, lesson in enumerate(day_data, 1):
            parts.append(_lesson_block(lesson, i))
            parts.append("")
    elif isinstance(day_data, str) and day_data.strip():
        has_group_lessons = True
        parts.append(day_data.strip())
        parts.append("")

    # Личные уроки
    if personal:
        for pl in personal:
            parts.append(_personal_block(pl))
            parts.append("")

    if not has_group_lessons and not personal:
        parts.append("<i>Занятий нет 🎉</i>")
        parts.append("")

    return "\n".join(parts)


# ═══════════════════════════════════════════
#   Публичные функции
# ═══════════════════════════════════════════

def format_today(schedule: dict, group_name: str, group_label: str,
                 personal_lessons: list = None) -> str:
    """Расписание на сегодня."""
    today = datetime.date.today()
    day_name = DAYS_RU[today.weekday()]

    title = (
        f"📋 <b>РАСПИСАНИЕ НА СЕГОДНЯ</b>\n"
        f"🎓 Курс: <b>{group_label}</b>\n\n"
    )

    group_data = schedule.get(group_name, {})
    day_data = group_data.get(day_name) or group_data.get(day_name.upper())

    today_personal = [
        l for l in (personal_lessons or [])
        if l['day_of_week'] == today.isoweekday()
    ]

    return title + _render_day(day_data, today, today_personal, show_divider=True)


def format_tomorrow(schedule: dict, group_name: str, group_label: str,
                    personal_lessons: list = None) -> str:
    """Расписание на завтра."""
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    day_name = DAYS_RU[tomorrow.weekday()]

    title = (
        f"📋 <b>РАСПИСАНИЕ НА ЗАВТРА</b>\n"
        f"🎓 Курс: <b>{group_label}</b>\n\n"
    )

    group_data = schedule.get(group_name, {})
    day_data = group_data.get(day_name) or group_data.get(day_name.upper())

    tmrw_personal = [
        l for l in (personal_lessons or [])
        if l['day_of_week'] == tomorrow.isoweekday()
    ]

    return title + _render_day(day_data, tomorrow, tmrw_personal, show_divider=True)


def format_week(schedule: dict, group_name: str, group_label: str,
                personal_lessons: list = None) -> str:
    """Расписание на всю неделю с отделением каждого дня."""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())

    title = (
        f"📋 <b>РАСПИСАНИЕ НА НЕДЕЛЮ</b>\n"
        f"🎓 Курс: <b>{group_label}</b>\n"
    )

    group_data = schedule.get(group_name, {})
    parts = [title]

    for i in range(6):  # Пн–Сб
        dt = monday + datetime.timedelta(days=i)
        day_name = DAYS_RU[i]
        day_data = group_data.get(day_name) or group_data.get(day_name.upper())

        day_personal = [
            l for l in (personal_lessons or [])
            if l['day_of_week'] == i + 1
        ]

        parts.append(_render_day(day_data, dt, day_personal, show_divider=True))

    return "\n".join(parts)


def format_personal_lessons(lessons: list) -> str:
    """Красивый вывод всех личных уроков."""
    if not lessons:
        return "📋 У вас пока нет личных уроков."

    lines = ["📋 <b>Ваши личные уроки</b>\n"]
    current_day = None

    for lesson in lessons:
        if lesson['day_of_week'] != current_day:
            current_day = lesson['day_of_week']
            lines.append(f"\n{DAY_DIVIDER}")
            lines.append(f"📆 <b>{lesson['day_name']}</b>")

        t = lesson['time_start']
        if lesson.get('time_end'):
            t += f" – {lesson['time_end']}"

        line = f"  🕐 <i>{t}</i> — <b>{lesson['subject']}</b>"
        if lesson.get('teacher'):
            line += f"\n     👤 {lesson['teacher']}"
        if lesson.get('room'):
            line += f"\n     🏫 ауд. <b>{lesson['room']}</b>"
        lines.append(line)

    return "\n".join(lines)
