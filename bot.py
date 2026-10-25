"""
Telegram-бот расписания Музыкального училища имени Гнесиных.

Улучшенная навигация:
- На каждом шаге добавления личного урока доступны кнопки «⬅️ Назад» и «🏠 Главное меню».
- Возможность вернуться на предыдущий шаг ввода в любой момент.
- Поддержка пропуска необязательных полей.
- Строгая привязка личных уроков к отделению и курсу.
"""

import os
import re
import logging
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import parser_module
import database as db
import formatter as fmt

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Состояния ConversationHandler (добавление урока) ──
ST_DAY, ST_TIME, ST_TIME_END, ST_SUBJECT, ST_TEACHER, ST_ROOM, ST_CONFIRM = range(7)


# ═══════════════════════════════════════════════════════
#   Клавиатуры
# ═══════════════════════════════════════════════════════

def kb_main_menu():
    """Главное меню."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="sch_today"),
            InlineKeyboardButton("📅 Завтра", callback_data="sch_tomorrow"),
        ],
        [InlineKeyboardButton("📅 На неделю", callback_data="sch_week")],
        [
            InlineKeyboardButton("➕ Добавить урок", callback_data="add_lesson"),
            InlineKeyboardButton("📋 Мои уроки", callback_data="my_lessons"),
        ],
        [InlineKeyboardButton("⚙️ Сменить группу", callback_data="settings")],
    ])


def kb_departments():
    """Выбор отделения."""
    depts = parser_module.get_department_list()
    buttons = []
    for dept_id, name in depts:
        short = name[:38]
        buttons.append([InlineKeyboardButton(short, callback_data=f"dept_{dept_id}")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def kb_groups(groups: list[str]):
    """Выбор курса/группы."""
    buttons = []
    for g in groups:
        buttons.append([InlineKeyboardButton(g, callback_data=f"grp_{g}")])
    buttons.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="settings"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(buttons)


def kb_days():
    """Выбор дня недели (Шаг 1)."""
    buttons = []
    for num, name in db.DAYS_OF_WEEK.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"day_{num}")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="cancel_to_menu")])
    return InlineKeyboardMarkup(buttons)


def kb_step_nav(can_skip: bool = False):
    """Клавиатура навигации для шагов ввода текста."""
    rows = []
    if can_skip:
        rows.append([InlineKeyboardButton("⏭ Пропустить", callback_data="skip")])
    rows.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="nav_back"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="cancel_to_menu"),
    ])
    return InlineKeyboardMarkup(rows)


def kb_back():
    """Стандартная кнопка возврата в меню."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
    ])


# ═══════════════════════════════════════════════════════
#   Утилиты
# ═══════════════════════════════════════════════════════

def _group_label(settings: dict) -> str:
    parts = [settings['dept_name']]
    if settings['group_name'] and settings['group_name'] != 'Все курсы':
        parts.append(settings['group_name'])
    return ", ".join(parts)


async def _send_long(send_func, text: str, reply_markup=None, parse_mode=None):
    MAX = 4096
    parts = []
    while text:
        if len(text) <= MAX:
            parts.append(text)
            break
        cut = text.rfind('\n\n', 0, MAX)
        if cut == -1:
            cut = text.rfind('\n', 0, MAX)
        if cut == -1:
            cut = MAX
        parts.append(text[:cut])
        text = text[cut:].lstrip('\n')

    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        await send_func(part, reply_markup=markup, parse_mode=parse_mode)


# ═══════════════════════════════════════════════════════
#   Стартовый флоу: выбор отделения → курса
# ═══════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if settings:
        label = _group_label(settings)
        text = f"🎵 <b>Гнесинка</b> | {label}\n\nЧто показать?"
        await update.message.reply_text(
            text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "🎵 <b>Добро пожаловать!</b>\n\n"
            "Бот расписания Музыкального училища\nимени Гнесиных.\n\n"
            "Для начала выберите ваше отделение:",
            reply_markup=kb_departments(),
            parse_mode=ParseMode.HTML,
        )


async def cb_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "⚙️ Выберите отделение:",
        reply_markup=kb_departments(),
    )


async def cb_select_dept(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    dept_id = q.data.replace("dept_", "")

    dept_name = parser_module.get_dept_name(dept_id)
    ctx.user_data['setup_dept_id'] = dept_id
    ctx.user_data['setup_dept_name'] = dept_name

    await q.edit_message_text(f"⏳ Загружаю расписание «{dept_name}»...")

    try:
        groups = parser_module.get_available_groups(dept_id)
    except Exception as e:
        logger.error(f"Ошибка получения групп: {e}")
        groups = ['1 курс']

    if len(groups) == 1:
        _save_and_show_menu(update.effective_user.id, dept_id, dept_name, groups[0])
        label = f"{dept_name}, {groups[0]}" if groups[0] != 'Все курсы' else dept_name
        await q.edit_message_text(
            f"✅ <b>Настройки сохранены!</b>\n\n"
            f"Группа: {label}\n\nЧто показать?",
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.HTML,
        )
    else:
        await q.edit_message_text(
            f"📚 <b>{dept_name}</b>\n\nВыберите ваш курс:",
            reply_markup=kb_groups(groups),
            parse_mode=ParseMode.HTML,
        )


async def cb_select_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    group_name = q.data.replace("grp_", "")

    dept_id = ctx.user_data.get('setup_dept_id', '01')
    dept_name = ctx.user_data.get('setup_dept_name', '')

    _save_and_show_menu(update.effective_user.id, dept_id, dept_name, group_name)

    label = _group_label({'dept_name': dept_name, 'group_name': group_name})
    await q.edit_message_text(
        f"✅ <b>Настройки сохранены!</b>\n\n"
        f"Группа: {label}\n\nЧто показать?",
        reply_markup=kb_main_menu(),
        parse_mode=ParseMode.HTML,
    )


def _save_and_show_menu(user_id, dept_id, dept_name, group_name):
    db.save_user_settings(user_id, dept_id, dept_name, group_name)


# ═══════════════════════════════════════════════════════
#   Показ расписания
# ═══════════════════════════════════════════════════════

async def cb_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if not settings:
        await q.edit_message_text(
            "⚠️ Сначала выберите отделение и курс.",
            reply_markup=kb_departments(),
        )
        return

    period = q.data

    await q.edit_message_text("⏳ Загружаю расписание...")

    try:
        schedule = parser_module.get_schedule_data(settings['dept_id'])
        personal = db.get_lessons(
            user_id,
            dept_id=settings['dept_id'],
            group_name=settings['group_name']
        )
        label = _group_label(settings)
        group = settings['group_name']

        if period == "sch_today":
            text = fmt.format_today(schedule, group, label, personal)
        elif period == "sch_tomorrow":
            text = fmt.format_tomorrow(schedule, group, label, personal)
        else:
            text = fmt.format_week(schedule, group, label, personal)

    except Exception as e:
        logger.error(f"Ошибка формирования расписания: {e}")
        text = "❌ Ошибка при загрузке расписания. Попробуйте позже."

    try:
        await q.delete_message()
    except Exception:
        pass

    await _send_long(
        q.message.chat.send_message,
        text,
        reply_markup=kb_main_menu(),
        parse_mode=ParseMode.HTML,
    )


async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if settings:
        label = _group_label(settings)
        text = f"🎵 <b>Гнесинка</b> | {label}\n\nЧто показать?"
        await q.edit_message_text(
            text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML
        )
    else:
        await q.edit_message_text(
            "Выберите отделение:", reply_markup=kb_departments()
        )


# ═══════════════════════════════════════════════════════
#   Просмотр личных уроков
# ═══════════════════════════════════════════════════════

async def cb_my_lessons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if settings:
        lessons = db.get_lessons(user_id, dept_id=settings['dept_id'], group_name=settings['group_name'])
        label = _group_label(settings)
        header = f"📋 <b>Ваши личные уроки ({label})</b>:\n"
    else:
        lessons = db.get_lessons(user_id)
        header = None

    text = fmt.format_personal_lessons(lessons)
    if header and lessons:
        text = header + "\n".join(text.split("\n")[1:])

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Удалить урок", callback_data="del_menu")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")],
    ])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def cmd_my(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)
    if settings:
        lessons = db.get_lessons(user_id, dept_id=settings['dept_id'], group_name=settings['group_name'])
        label = _group_label(settings)
        header = f"📋 <b>Ваши личные уроки ({label})</b>:\n"
    else:
        lessons = db.get_lessons(user_id)
        header = None

    text = fmt.format_personal_lessons(lessons)
    if header and lessons:
        text = header + "\n".join(text.split("\n")[1:])

    await update.message.reply_text(
        text, reply_markup=kb_back(), parse_mode=ParseMode.HTML
    )


# ═══════════════════════════════════════════════════════
#   Удаление уроков
# ═══════════════════════════════════════════════════════

async def cb_del_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if settings:
        lessons = db.get_lessons(user_id, dept_id=settings['dept_id'], group_name=settings['group_name'])
    else:
        lessons = db.get_lessons(user_id)

    if not lessons:
        await q.edit_message_text(
            "📋 Нет уроков для удаления.", reply_markup=kb_back()
        )
        return

    buttons = []
    for l in lessons:
        day_short = l['day_name'][:3]
        label = f"❌ {day_short} {l['time_start']} — {l['subject']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"del_{l['id']}")])
    buttons.append([InlineKeyboardButton("🗑 Удалить все для этого курса", callback_data="del_all")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu")])

    await q.edit_message_text(
        "🗑 Выберите урок для удаления:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if q.data == "del_all":
        if settings:
            n = db.delete_all_lessons(user_id, dept_id=settings['dept_id'], group_name=settings['group_name'])
        else:
            n = db.delete_all_lessons(user_id)
        await q.edit_message_text(
            f"✅ Удалено уроков: {n}", reply_markup=kb_back()
        )
    else:
        lesson_id = int(q.data.replace("del_", ""))
        if db.delete_lesson(user_id, lesson_id):
            await q.edit_message_text("✅ Урок удалён!", reply_markup=kb_back())
        else:
            await q.edit_message_text("⚠️ Урок не найден.", reply_markup=kb_back())


# ═══════════════════════════════════════════════════════
#   Добавление урока с поддержкой навигации
# ═══════════════════════════════════════════════════════

async def render_step_prompt(step: int, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Генератор экрана для каждого шага добавления урока."""
    d = ctx.user_data.get('new', {})
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)
    label = _group_label(settings) if settings else ''

    if step == ST_DAY:
        text = f"➕ <b>Новый личный урок</b>\nКурс: <i>{label}</i>\n\n1️⃣ Выберите день недели:"
        kb = kb_days()
    elif step == ST_TIME:
        day_name = db.DAYS_OF_WEEK.get(d.get('day', 1), 'Понедельник')
        text = f"📆 День: <b>{day_name}</b>\n\n2️⃣ Введите время начала (например: <b>14:30</b>):"
        kb = kb_step_nav(can_skip=False)
    elif step == ST_TIME_END:
        t1 = d.get('time_start', '')
        text = f"🕐 Начало: <b>{t1}</b>\n\n3️⃣ Введите время окончания (или «Пропустить»):"
        kb = kb_step_nav(can_skip=True)
    elif step == ST_SUBJECT:
        text = "4️⃣ Введите название предмета (например: <i>Специальность — вокал</i>):"
        kb = kb_step_nav(can_skip=False)
    elif step == ST_TEACHER:
        sub = d.get('subject', '')
        text = f"📝 Предмет: <b>{sub}</b>\n\n5️⃣ Введите ФИО преподавателя (или «Пропустить»):"
        kb = kb_step_nav(can_skip=True)
    elif step == ST_ROOM:
        text = "6️⃣ Введите номер аудитории (или «Пропустить»):"
        kb = kb_step_nav(can_skip=True)
    elif step == ST_CONFIRM:
        text = _preview(d)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Сохранить", callback_data="confirm")],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="nav_back"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="cancel_to_menu"),
            ]
        ])

    if update.callback_query:
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


def _preview(d: dict) -> str:
    day = db.DAYS_OF_WEEK.get(d.get('day', 1), 'Понедельник')
    t = d.get('time_start', '')
    if d.get('time_end'):
        t += f"–{d['time_end']}"
    lines = [
        "📋 <b>Проверьте данные урока:</b>\n",
        f"📆 День: {day}",
        f"🕐 Время: {t}",
        f"📝 Предмет: {d.get('subject', '')}",
    ]
    if d.get('teacher'):
        lines.append(f"👤 Преподаватель: {d['teacher']}")
    if d.get('room'):
        lines.append(f"🏫 Аудитория: {d['room']}")
    lines.append("\nВсё верно?")
    return "\n".join(lines)


async def cancel_to_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Выход из создания урока в главное меню."""
    ctx.user_data.pop('new', None)
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    text = "🏠 Главное меню"
    kb = kb_main_menu()
    if settings:
        label = _group_label(settings)
        text = f"🎵 <b>Гнесинка</b> | {label}\n\nЧто показать?"

    if update.callback_query:
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

    return ConversationHandler.END


# ── Хэндлеры шагов ──

async def add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)

    if not settings:
        text = "⚠️ Сначала выберите отделение и курс в меню /start!"
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=kb_back())
        else:
            await update.message.reply_text(text, reply_markup=kb_back())
        return ConversationHandler.END

    ctx.user_data['new'] = {
        'dept_id': settings['dept_id'],
        'group_name': settings['group_name']
    }
    await render_step_prompt(ST_DAY, update, ctx)
    return ST_DAY


async def add_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    if q.data == "cancel_to_menu":
        return await cancel_to_menu(update, ctx)

    day = int(q.data.replace("day_", ""))
    ctx.user_data['new']['day'] = day
    await render_step_prompt(ST_TIME, update, ctx)
    return ST_TIME


async def add_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace('.', ':')
    if not re.match(r'^\d{1,2}:\d{2}$', text):
        await update.message.reply_text(
            "⚠️ Неверный формат! Введите время в формате ЧЧ:ММ (например: <b>14:30</b>):",
            reply_markup=kb_step_nav(can_skip=False),
            parse_mode=ParseMode.HTML
        )
        return ST_TIME

    ctx.user_data['new']['time_start'] = text
    await render_step_prompt(ST_TIME_END, update, ctx)
    return ST_TIME_END


async def add_time_nav(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q.data == "nav_back":
        await render_step_prompt(ST_DAY, update, ctx)
        return ST_DAY
    return await cancel_to_menu(update, ctx)


async def add_time_end(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace('.', ':')
    if not re.match(r'^\d{1,2}:\d{2}$', text):
        await update.message.reply_text(
            "⚠️ Введите время в формате ЧЧ:ММ или нажмите «Пропустить»:",
            reply_markup=kb_step_nav(can_skip=True),
            parse_mode=ParseMode.HTML
        )
        return ST_TIME_END

    ctx.user_data['new']['time_end'] = text
    await render_step_prompt(ST_SUBJECT, update, ctx)
    return ST_SUBJECT


async def add_time_end_nav(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q.data == "nav_back":
        await render_step_prompt(ST_TIME, update, ctx)
        return ST_TIME
    elif q.data == "skip":
        ctx.user_data['new']['time_end'] = None
        await render_step_prompt(ST_SUBJECT, update, ctx)
        return ST_SUBJECT
    return await cancel_to_menu(update, ctx)


async def add_subject(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data['new']['subject'] = update.message.text.strip()
    await render_step_prompt(ST_TEACHER, update, ctx)
    return ST_TEACHER


async def add_subject_nav(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q.data == "nav_back":
        await render_step_prompt(ST_TIME_END, update, ctx)
        return ST_TIME_END
    return await cancel_to_menu(update, ctx)


async def add_teacher(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data['new']['teacher'] = update.message.text.strip()
    await render_step_prompt(ST_ROOM, update, ctx)
    return ST_ROOM


async def add_teacher_nav(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q.data == "nav_back":
        await render_step_prompt(ST_SUBJECT, update, ctx)
        return ST_SUBJECT
    elif q.data == "skip":
        ctx.user_data['new']['teacher'] = None
        await render_step_prompt(ST_ROOM, update, ctx)
        return ST_ROOM
    return await cancel_to_menu(update, ctx)


async def add_room(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data['new']['room'] = update.message.text.strip()
    await render_step_prompt(ST_CONFIRM, update, ctx)
    return ST_CONFIRM


async def add_room_nav(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q.data == "nav_back":
        await render_step_prompt(ST_TEACHER, update, ctx)
        return ST_TEACHER
    elif q.data == "skip":
        ctx.user_data['new']['room'] = None
        await render_step_prompt(ST_CONFIRM, update, ctx)
        return ST_CONFIRM
    return await cancel_to_menu(update, ctx)


async def add_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q.data == "nav_back":
        await render_step_prompt(ST_ROOM, update, ctx)
        return ST_ROOM
    elif q.data == "cancel_to_menu":
        return await cancel_to_menu(update, ctx)

    await q.answer()
    d = ctx.user_data.pop('new', {})
    try:
        db.add_lesson(
            user_id=update.effective_user.id,
            day_of_week=d['day'],
            time_start=d['time_start'],
            subject=d['subject'],
            teacher=d.get('teacher'),
            room=d.get('room'),
            time_end=d.get('time_end'),
            dept_id=d.get('dept_id'),
            group_name=d.get('group_name'),
        )
        await q.edit_message_text("✅ Личный урок сохранён!", reply_markup=kb_back())
    except Exception as e:
        logger.error(f"Ошибка сохранения урока: {e}")
        await q.edit_message_text("❌ Ошибка сохранения.", reply_markup=kb_back())
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════
#   Команды-ярлыки
# ═══════════════════════════════════════════════════════

async def cmd_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)
    if not settings:
        await update.message.reply_text(
            "⚠️ Сначала настройте группу: /start"
        )
        return
    label = _group_label(settings)
    await update.message.reply_text(
        f"🎵 <b>{label}</b>\n\nВыберите период:",
        reply_markup=kb_main_menu(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Команды бота</b>\n\n"
        "/start — Главное меню / Настройка курса\n"
        "/schedule — Выбор периода расписания\n"
        "/add — Добавить личный урок\n"
        "/my — Мои личные уроки\n"
        "/update — Обновить расписание с сайта\n"
        "/help — Справка",
        parse_mode=ParseMode.HTML,
    )


async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Обновляю расписание...")
    try:
        parser_module.update_cache()
        t = parser_module.get_last_update_time()
        await update.message.reply_text(
            f"✅ Обновлено!\n🕐 {t}", reply_markup=kb_back()
        )
    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await update.message.reply_text("❌ Ошибка обновления.")


# ═══════════════════════════════════════════════════════
#   Запуск
# ═══════════════════════════════════════════════════════

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN не задан! Создайте .env файл.")
        return

    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CallbackQueryHandler(add_start, pattern=r"^add_lesson$"),
        ],
        states={
            ST_DAY: [
                CallbackQueryHandler(add_day, pattern=r"^day_\d+$"),
                CallbackQueryHandler(cancel_to_menu, pattern=r"^cancel_to_menu$"),
            ],
            ST_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_time),
                CallbackQueryHandler(add_time_nav, pattern=r"^(nav_back|cancel_to_menu)$"),
            ],
            ST_TIME_END: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_time_end),
                CallbackQueryHandler(add_time_end_nav, pattern=r"^(skip|nav_back|cancel_to_menu)$"),
            ],
            ST_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_subject),
                CallbackQueryHandler(add_subject_nav, pattern=r"^(nav_back|cancel_to_menu)$"),
            ],
            ST_TEACHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_teacher),
                CallbackQueryHandler(add_teacher_nav, pattern=r"^(skip|nav_back|cancel_to_menu)$"),
            ],
            ST_ROOM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_room),
                CallbackQueryHandler(add_room_nav, pattern=r"^(skip|nav_back|cancel_to_menu)$"),
            ],
            ST_CONFIRM: [
                CallbackQueryHandler(add_confirm, pattern=r"^(confirm|nav_back|cancel_to_menu)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_to_menu),
            CallbackQueryHandler(cancel_to_menu, pattern=r"^cancel_to_menu$"),
        ],
        per_message=False,
    )
    app.add_handler(conv)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CommandHandler("my", cmd_my))

    app.add_handler(CallbackQueryHandler(cb_schedule, pattern=r"^sch_"))
    app.add_handler(CallbackQueryHandler(cb_my_lessons, pattern=r"^my_lessons$"))
    app.add_handler(CallbackQueryHandler(cb_del_menu, pattern=r"^del_menu$"))
    app.add_handler(CallbackQueryHandler(cb_delete, pattern=r"^del_"))
    app.add_handler(CallbackQueryHandler(cb_select_dept, pattern=r"^dept_"))
    app.add_handler(CallbackQueryHandler(cb_select_group, pattern=r"^grp_"))
    app.add_handler(CallbackQueryHandler(cb_settings, pattern=r"^settings$"))
    app.add_handler(CallbackQueryHandler(cb_menu, pattern=r"^menu$"))

    logger.info("🎵 Бот расписания Гнесинки запущен!")
    app.run_polling()


if __name__ == '__main__':
    main()
