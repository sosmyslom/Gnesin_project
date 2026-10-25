"""
Модуль для работы с базой данных.
- Настройки пользователя (отделение, курс)
- Личные уроки по специальности (привязаны к отделению и курсу)
"""

import os
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')

DAYS_OF_WEEK = {
    1: 'Понедельник',
    2: 'Вторник',
    3: 'Среда',
    4: 'Четверг',
    5: 'Пятница',
    6: 'Суббота',
    7: 'Воскресенье',
}


def _get_connection() -> sqlite3.Connection:
    """Подключение к БД с автосозданием таблиц и миграцией."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            dept_id TEXT NOT NULL,
            dept_name TEXT NOT NULL,
            group_name TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS personal_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dept_id TEXT,
            group_name TEXT,
            day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 1 AND 7),
            time_start TEXT NOT NULL,
            time_end TEXT,
            subject TEXT NOT NULL,
            teacher TEXT,
            room TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_lessons_user
            ON personal_lessons(user_id);
    """)

    # Миграция колонок для старых БД
    try:
        conn.execute("ALTER TABLE personal_lessons ADD COLUMN dept_id TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE personal_lessons ADD COLUMN group_name TEXT")
    except Exception:
        pass

    return conn


# ═══════════════════════════════════════════
#   Настройки пользователя
# ═══════════════════════════════════════════

def get_user_settings(user_id: int) -> Optional[dict]:
    """Возвращает {'dept_id', 'dept_name', 'group_name'} или None."""
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT dept_id, dept_name, group_name FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            return {'dept_id': row[0], 'dept_name': row[1], 'group_name': row[2]}
        return None
    finally:
        conn.close()


def save_user_settings(user_id: int, dept_id: str, dept_name: str, group_name: str):
    """Сохраняет или обновляет настройки пользователя."""
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT INTO user_settings (user_id, dept_id, dept_name, group_name)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   dept_id   = excluded.dept_id,
                   dept_name = excluded.dept_name,
                   group_name = excluded.group_name,
                   updated_at = CURRENT_TIMESTAMP""",
            (user_id, dept_id, dept_name, group_name),
        )
        conn.commit()
    finally:
        conn.close()


def clear_user_settings(user_id: int):
    """Удаляет настройки пользователя."""
    conn = _get_connection()
    try:
        conn.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════
#   Личные уроки
# ═══════════════════════════════════════════

def add_lesson(user_id: int, day_of_week: int, time_start: str, subject: str,
               teacher: str = None, room: str = None, time_end: str = None,
               dept_id: str = None, group_name: str = None) -> int:
    """Добавляет личный урок с привязкой к отделению и курсу."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO personal_lessons
               (user_id, dept_id, group_name, day_of_week, time_start, time_end, subject, teacher, room)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, dept_id, group_name, day_of_week, time_start, time_end, subject, teacher, room),
        )
        conn.commit()
        logger.info(f"Добавлен урок #{cur.lastrowid} для user {user_id} ({dept_id}/{group_name})")
        return cur.lastrowid
    finally:
        conn.close()


def get_lessons(user_id: int, day_of_week: Optional[int] = None,
                dept_id: Optional[str] = None, group_name: Optional[str] = None) -> list[dict]:
    """
    Возвращает список уроков пользователя.
    Если указаны dept_id и group_name — только уроки для данного отделения и курса.
    """
    conn = _get_connection()
    try:
        query = ("SELECT id, day_of_week, time_start, time_end, subject, teacher, room, dept_id, group_name "
                 "FROM personal_lessons WHERE user_id = ?")
        params = [user_id]

        if dept_id is not None and group_name is not None:
            query += " AND (dept_id = ? AND group_name = ?)"
            params.extend([dept_id, group_name])
        elif dept_id is not None:
            query += " AND (dept_id = ?)"
            params.append(dept_id)

        if day_of_week is not None:
            query += " AND day_of_week = ?"
            params.append(day_of_week)

        query += " ORDER BY day_of_week, time_start"

        rows = conn.execute(query, params).fetchall()
        return [
            {
                'id': r[0], 'day_of_week': r[1],
                'day_name': DAYS_OF_WEEK.get(r[1], '?'),
                'time_start': r[2], 'time_end': r[3],
                'subject': r[4], 'teacher': r[5], 'room': r[6],
                'dept_id': r[7], 'group_name': r[8],
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_lesson(user_id: int, lesson_id: int) -> bool:
    """Удаляет урок по ID (только свой)."""
    conn = _get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM personal_lessons WHERE id = ? AND user_id = ?",
            (lesson_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_all_lessons(user_id: int, dept_id: Optional[str] = None, group_name: Optional[str] = None) -> int:
    """Удаляет уроки пользователя (опционально по отделению/курсу)."""
    conn = _get_connection()
    try:
        if dept_id is not None and group_name is not None:
            cur = conn.execute(
                "DELETE FROM personal_lessons WHERE user_id = ? AND dept_id = ? AND group_name = ?",
                (user_id, dept_id, group_name),
            )
        else:
            cur = conn.execute(
                "DELETE FROM personal_lessons WHERE user_id = ?", (user_id,),
            )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
