import { api } from 'sdk';
import {
  getUserSettings,
  saveUserSettings,
  updateUserFilters,
  setAutoSchedule,
  updateAutoScheduleTime,
  groupLabel,
  getPersonalLessons,
  deleteLesson,
  deleteAllLessons,
  setScheduleFormat,
  toggleScheduleFormat,
} from '../lib/user.js';
import { getDeptName, DEPARTMENTS, EDU_LEVELS } from '../lib/departments.js';
import { getScheduleForDept, getAvailableGroups } from '../lib/schedule.js';
import {
  kbMainMenu,
  kbEduLevels,
  kbDepartments,
  kbGroups,
  kbBack,
  kbStepNav,
  kbReplyKeyboard,
  kbFilterSettings,
  kbAutoScheduleMenu,
  kbAutoTimeInput,
  kbPhotoMenu,
  kbPhotoDatePicker,
  kbPhotoViewActions,
  kbDatePicker,
} from '../lib/keyboards.js';
import {
  formatToday,
  formatTomorrow,
  formatWeek,
  formatSpecificDay,
  formatPersonalLessons,
} from '../lib/formatter.js';
import { scheduleImages } from '../lib/image_manifest.js';
import {
  STEPS,
  getUserState,
  saveUserState,
  clearUserState,
  getStepPrompt,
  finalizeLesson,
} from '../lib/wizard.js';
import { sendLong } from '../lib/telegram_util.js';
import { sendUserAutoSchedule } from '../lib/auto_sender.js';
import { sendPhotoSchedule, sendTextSchedule } from '../lib/schedule_sender.js';

/**
 * Безопасно редактирует сообщение или удаляет его и отправляет новое,
 * если исходное сообщение было медиа (фото/документ), так как Telegram
 * не разрешает превращать фото-сообщение в текстовое через editMessageText.
 */
async function editOrSend(query, { text, reply_markup, parse_mode = 'HTML' }) {
  const chatId = query.message?.chat?.id;
  const messageId = query.message?.message_id;
  const isMedia = Boolean(query.message?.photo || query.message?.document || !query.message?.text);

  if (isMedia) {
    if (messageId) {
      try {
        await api.deleteMessage({ chat_id: chatId, message_id: messageId });
      } catch (e) {}
    }
    return await api.sendMessage({
      chat_id: chatId,
      text,
      reply_markup,
      parse_mode,
    });
  }

  try {
    return await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text,
      reply_markup,
      parse_mode,
    });
  } catch (err) {
    if (err?.message?.includes('message is not modified')) {
      return;
    }
    try {
      if (messageId) await api.deleteMessage({ chat_id: chatId, message_id: messageId });
    } catch (e) {}
    return await api.sendMessage({
      chat_id: chatId,
      text,
      reply_markup,
      parse_mode,
    });
  }
}

export default async function (query, ctx) {
  if (!query || !query.data) return;

  const callbackData = query.data;
  const userId = query.from.id;
  const chatId = query.message?.chat?.id;
  const messageId = query.message?.message_id;

  // Всегда подтверждаем callback, чтобы у пользователя снялась анимация загрузки
  try {
    await api.answerCallbackQuery({ callback_query_id: query.id });
  } catch (err) {
    console.warn('answerCallbackQuery error:', err.message);
  }

  // 1. Возврат в главное меню
  if (callbackData === 'menu') {
    const settings = await getUserSettings(userId);
    if (settings) {
      const label = groupLabel(settings);
      await editOrSend(query, {
        text: `🎵 <b>Гнесинка</b> | ${label}\n\nЧто показать?`,
        reply_markup: kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, settings.scheduleFormat),
      });
    } else {
      await editOrSend(query, {
        text:
          '🎓 <b>Добро пожаловать!</b>\n\n' +
          'Выберите ступень образования:\n' +
          '• <b>СПО</b> — Музыкальное училище имени Гнесиных\n' +
          '• <b>Бакалавриат, Специалитет, Магистратура</b> (РАМ)',
        reply_markup: kbEduLevels(),
      });
    }
    return;
  }

  // Меню авторасписания
  if (callbackData === 'auto_schedule_menu') {
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '🎓 Сначала выберите ступень образования и группу:',
        reply_markup: kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }

    const enabled = Boolean(settings.autoSchedule);
    const time = settings.autoScheduleTime || '08:00';
    const statusText = enabled
      ? `🔔 <b>Включено</b> (Пн–Сб в <b>${time}</b>, вс — выходной)`
      : `🔕 <b>Отключено</b> (по умолчанию — <b>${time}</b>)`;

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `⏰ <b>Авторасписание</b>\n\nСтатус: ${statusText}`,
      reply_markup: kbAutoScheduleMenu(enabled, time),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData === 'auto_enable') {
    await setAutoSchedule(userId, true);
    const settings = await getUserSettings(userId);
    const time = settings?.autoScheduleTime || '08:00';

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `⏰ <b>Авторасписание</b>\n\nСтатус: 🔔 <b>Включено</b> (Пн–Сб в <b>${time}</b>, вс — выходной)`,
      reply_markup: kbAutoScheduleMenu(true, time),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData === 'auto_disable') {
    await setAutoSchedule(userId, false);
    const settings = await getUserSettings(userId);
    const time = settings?.autoScheduleTime || '08:00';

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `⏰ <b>Авторасписание</b>\n\nСтатус: 🔕 <b>Отключено</b> (по умолчанию — <b>${time}</b>)`,
      reply_markup: kbAutoScheduleMenu(false, time),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData.startsWith('auto_set_') && callbackData !== 'auto_set_time') {
    const selectedTime = callbackData.replace('auto_set_', '');
    await updateAutoScheduleTime(userId, selectedTime);

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `⏰ <b>Авторасписание</b>\n\nСтатус: 🔔 <b>Включено</b> (Пн–Сб в <b>${selectedTime}</b>, вс — выходной)`,
      reply_markup: kbAutoScheduleMenu(true, selectedTime),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData === 'auto_set_time') {
    await saveUserState(userId, STEPS.AUTO_TIME, {});

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: '⏰ <b>Ввод времени</b>\n\nОтправьте время в формате <b>ЧЧ:ММ</b> (например: <code>07:30</code> или <code>09:00</code>):',
      reply_markup: kbAutoTimeInput(),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData === 'auto_test_send') {
    await sendUserAutoSchedule(userId, true);
    try {
      await api.answerCallbackQuery({
        callback_query_id: query.id,
        text: 'Тестовое расписание отправлено!',
        show_alert: false,
      });
    } catch (e) {}
    return;
  }

  // 2. Настройки (выбор ступени образования)
  if (callbackData === 'settings' || callbackData === 'choose_level') {
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text:
        '🎓 <b>Выберите ступень образования:</b>\n\n' +
        '• <b>СПО</b> — Музыкальное училище имени Гнесиных\n' +
        '• <b>Бакалавриат, Специалитет, Магистратура</b> (РАМ)',
      reply_markup: kbEduLevels(),
      parse_mode: 'HTML',
    });
    return;
  }

  // 2.1. Выбор конкретной ступени
  if (callbackData.startsWith('lvl_')) {
    const levelKey = callbackData.replace('lvl_', '');
    const levelInfo = EDU_LEVELS[levelKey];
    const title = levelInfo ? levelInfo.name : 'Выберите направление / профиль:';
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `📚 <b>${title}</b>\n\nВыберите направление / профиль:`,
      reply_markup: kbDepartments(levelKey),
      parse_mode: 'HTML',
    });
    return;
  }

  // 3. Выбор отделения
  if (callbackData.startsWith('dept_')) {
    const deptId = callbackData.replace('dept_', '');
    const deptName = getDeptName(deptId);
    const deptInfo = DEPARTMENTS[deptId];
    const level = deptInfo?.level || null;

    const groups = await getAvailableGroups(deptId);

    if (groups.length === 1) {
      await saveUserSettings(userId, deptId, deptName, groups[0]);
      await clearUserState(userId);
      const settings = await getUserSettings(userId);
      const label = groups[0] !== 'Все курсы' ? `${deptName}, ${groups[0]}` : deptName;
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: `✅ <b>Настройки сохранены!</b>\n\nГруппа: ${label}\n\nЧто показать?`,
        reply_markup: kbMainMenu(userId, settings?.autoSchedule, settings?.autoScheduleTime, settings?.scheduleFormat),
        parse_mode: 'HTML',
      });
      try {
        await api.sendMessage({
          chat_id: chatId,
          text: 'Кнопки быстрого доступа закреплены внизу чата ⬇️',
          reply_markup: kbReplyKeyboard(),
        });
      } catch (e) {}
    } else {
      await saveUserState(userId, 'SETUP_GROUP', { dept_id: deptId, dept_name: deptName, level });
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: `📚 <b>${deptName}</b>\n\nВыберите ваш курс:`,
        reply_markup: kbGroups(groups, level),
        parse_mode: 'HTML',
      });
    }
    return;
  }

  // 4. Выбор группы/курса
  if (callbackData.startsWith('grp_')) {
    const groupName = callbackData.replace('grp_', '');
    const state = await getUserState(userId);
    const deptId = state?.data?.dept_id || '01';
    const deptName = state?.data?.dept_name || getDeptName(deptId);

    await saveUserSettings(userId, deptId, deptName, groupName);
    await clearUserState(userId);
    const settings = await getUserSettings(userId);

    const label = groupLabel({ deptName, groupName });
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `✅ <b>Настройки сохранены!</b>\n\nГруппа: ${label}\n\nЧто показать?`,
      reply_markup: kbMainMenu(userId, settings?.autoSchedule, settings?.autoScheduleTime, settings?.scheduleFormat),
      parse_mode: 'HTML',
    });

    try {
      await api.sendMessage({
        chat_id: chatId,
        text: 'Кнопки быстрого доступа закреплены внизу чата ⬇️',
        reply_markup: kbReplyKeyboard(),
      });
    } catch (e) {}
    return;
  }

  // 5. Переключение формата и меню фото
  if (callbackData === 'set_fmt_photo' || callbackData === 'photo_menu' || callbackData === 'sch_img') {
    await setScheduleFormat(userId, 'photo');
    const settings = await getUserSettings(userId);
    if (!settings) {
      await editOrSend(query, {
        text: '🎓 Сначала выберите ступень образования и группу:',
        reply_markup: kbEduLevels(),
      });
      return;
    }

    const label = groupLabel(settings);
    await editOrSend(query, {
      text: `📸 <b>Расписание по фото</b> | <i>${label}</i>\n\nВыберите вариант:`,
      reply_markup: kbPhotoMenu(),
    });
    return;
  }

  if (callbackData === 'set_fmt_text') {
    await setScheduleFormat(userId, 'text');
    const settings = await getUserSettings(userId);
    if (!settings) return;
    const label = groupLabel(settings);
    await editOrSend(query, {
      text: `🎵 <b>Гнесинка</b> | ${label}\n\nРежим переключен на <b>текстовый</b> 📝\nЧто показать?`,
      reply_markup: kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, 'text'),
    });
    return;
  }

  if (callbackData === 'photo_pick_date') {
    const settings = await getUserSettings(userId);
    if (!settings) return;
    const label = groupLabel(settings);
    await editOrSend(query, {
      text: `📆 <b>Расписание по фото на день</b> | <i>${label}</i>\n\nВыберите нужный день недели:`,
      reply_markup: kbPhotoDatePicker(),
    });
    return;
  }

  if (callbackData === 'photo_today') {
    const settings = await getUserSettings(userId);
    if (!settings) return;
    const now = new Date(Date.now() + 3 * 3600 * 1000);
    const day = now.getUTCDay();
    await sendPhotoSchedule(settings, chatId, messageId, day, 'сегодня');
    return;
  }

  if (callbackData === 'photo_tomorrow') {
    const settings = await getUserSettings(userId);
    if (!settings) return;
    const now = new Date(Date.now() + 3 * 3600 * 1000);
    const day = (now.getUTCDay() + 1) % 7;
    await sendPhotoSchedule(settings, chatId, messageId, day, 'завтра');
    return;
  }

  if (callbackData === 'photo_week') {
    const settings = await getUserSettings(userId);
    if (!settings) return;
    await sendPhotoSchedule(settings, chatId, messageId, null);
    return;
  }

  if (callbackData.startsWith('photo_day_')) {
    const settings = await getUserSettings(userId);
    if (!settings) return;
    const dayNum = parseInt(callbackData.replace('photo_day_', ''), 10);
    await sendPhotoSchedule(settings, chatId, messageId, dayNum);
    return;
  }

  if (callbackData === 'noop') {
    return;
  }

  // Фильтры расписания (бюджет/платное, подгруппа 1/2/3)
  if (callbackData === 'filters_menu') {
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '🎓 Сначала выберите ступень образования и группу:',
        reply_markup: kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }

    const label = groupLabel(settings);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text:
        `🎯 <b>Фильтр расписания</b>\n` +
        `🎓 Группа: <b>${label}</b>\n\n` +
        `Скройте чужие пары (общие лекции показываются всегда):\n` +
        `• <b>Обучение</b>: Бюджет или Платное\n` +
        `• <b>Подгруппа</b>: 1 (А), 2 (Б), 3 (В)\n\n` +
        `Нажимайте на кнопки ниже, чтобы переключить фильтры:`,
      reply_markup: kbFilterSettings(settings.subgroup, settings.funding),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData.startsWith('set_fd_')) {
    const fundingVal = callbackData.replace('set_fd_', '');
    await updateUserFilters(userId, undefined, fundingVal);
    const settings = await getUserSettings(userId);
    const label = groupLabel(settings);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text:
        `🎯 <b>Фильтр расписания</b>\n` +
        `🎓 Группа: <b>${label}</b>\n\n` +
        `Скройте чужие пары (общие лекции показываются всегда):\n` +
        `• <b>Обучение</b>: Бюджет или Платное\n` +
        `• <b>Подгруппа</b>: 1 (А), 2 (Б), 3 (В)\n\n` +
        `Нажимайте на кнопки ниже, чтобы переключить фильтры:`,
      reply_markup: kbFilterSettings(settings?.subgroup, settings?.funding),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData.startsWith('set_sg_')) {
    const subgroupVal = callbackData.replace('set_sg_', '');
    await updateUserFilters(userId, subgroupVal, undefined);
    const settings = await getUserSettings(userId);
    const label = groupLabel(settings);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text:
        `🎯 <b>Фильтр расписания</b>\n` +
        `🎓 Группа: <b>${label}</b>\n\n` +
        `Скройте чужие пары (общие лекции показываются всегда):\n` +
        `• <b>Обучение</b>: Бюджет или Платное\n` +
        `• <b>Подгруппа</b>: 1 (А), 2 (Б), 3 (В)\n\n` +
        `Нажимайте на кнопки ниже, чтобы переключить фильтры:`,
      reply_markup: kbFilterSettings(settings?.subgroup, settings?.funding),
      parse_mode: 'HTML',
    });
    return;
  }

  // 6. Показ расписания (сегодня, завтра, неделя, день)
  if (callbackData.startsWith('sch_')) {
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '🎓 Сначала выберите ступень образования и группу:',
        reply_markup: kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }

    if (settings.scheduleFormat === 'photo') {
      if (callbackData === 'sch_week') {
        await sendPhotoSchedule(settings, chatId, messageId, null);
        return;
      }
      if (callbackData === 'sch_today') {
        const now = new Date(Date.now() + 3 * 3600 * 1000);
        const day = now.getUTCDay();
        await sendPhotoSchedule(settings, chatId, messageId, day, 'сегодня');
        return;
      }
      if (callbackData === 'sch_tomorrow') {
        const now = new Date(Date.now() + 3 * 3600 * 1000);
        const day = (now.getUTCDay() + 1) % 7;
        await sendPhotoSchedule(settings, chatId, messageId, day, 'завтра');
        return;
      }
      if (callbackData.startsWith('sch_day_')) {
        const dayNum = parseInt(callbackData.replace('sch_day_', ''), 10);
        await sendPhotoSchedule(settings, chatId, messageId, dayNum);
        return;
      }
    }

    await sendTextSchedule(settings, chatId, messageId, callbackData);
    return;
  }

  // 6. Просмотр личных уроков
  if (callbackData === 'my_lessons') {
    const settings = await getUserSettings(userId);
    let lessons = [];
    let header = null;

    if (settings) {
      lessons = await getPersonalLessons(userId, settings.deptId, settings.groupName);
      const label = groupLabel(settings);
      header = `📋 <b>Ваши личные уроки (${label})</b>:\n`;
    } else {
      lessons = await getPersonalLessons(userId);
    }

    let text = formatPersonalLessons(lessons);
    if (header && lessons && lessons.length > 0) {
      text = header + text.split('\n').slice(1).join('\n');
    }

    const kb = {
      inline_keyboard: [
        [{ text: '🗑 Удалить урок', callback_data: 'del_menu' }],
        [{ text: '🏠 Главное меню', callback_data: 'menu' }],
      ],
    };

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text,
      reply_markup: kb,
      parse_mode: 'HTML',
    });
    return;
  }

  // 7. Меню удаления уроков
  if (callbackData === 'del_menu') {
    const settings = await getUserSettings(userId);
    const lessons = settings
      ? await getPersonalLessons(userId, settings.deptId, settings.groupName)
      : await getPersonalLessons(userId);

    if (!lessons || lessons.length === 0) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '📋 Нет уроков для удаления.',
        reply_markup: kbBack(),
        parse_mode: 'HTML',
      });
      return;
    }

    const buttons = [];
    for (const l of lessons) {
      const dayShort = (l.day_name || 'Пн').slice(0, 3);
      const tStart = l.timeStart || l.time_start;
      const label = `❌ ${dayShort} ${tStart} — ${l.subject}`;
      buttons.push([{ text: label, callback_data: `del_${l.id}` }]);
    }
    buttons.push([{ text: '🗑 Удалить все для этого курса', callback_data: 'del_all' }]);
    buttons.push([{ text: '🏠 Главное меню', callback_data: 'menu' }]);

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: '🗑 Выберите урок для удаления:',
      reply_markup: { inline_keyboard: buttons },
      parse_mode: 'HTML',
    });
    return;
  }

  // 8. Удаление уроков (всех или одного)
  if (callbackData === 'del_all') {
    const settings = await getUserSettings(userId);
    const n = settings
      ? await deleteAllLessons(userId, settings.deptId, settings.groupName)
      : await deleteAllLessons(userId);

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: `✅ Удалено уроков: ${n}`,
      reply_markup: kbBack(),
      parse_mode: 'HTML',
    });
    return;
  }

  if (callbackData.startsWith('del_')) {
    const lessonId = parseInt(callbackData.replace('del_', ''), 10);
    const ok = await deleteLesson(userId, lessonId);

    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: ok ? '✅ Урок удалён!' : '⚠️ Урок не найден.',
      reply_markup: kbBack(),
      parse_mode: 'HTML',
    });
    return;
  }

  // 9. Добавление личного урока: старт
  if (callbackData === 'add_lesson') {
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '⚠️ Сначала выберите отделение и курс в меню /start!',
        reply_markup: kbBack(),
        parse_mode: 'HTML',
      });
      return;
    }

    const initialData = {
      dept_id: settings.deptId,
      group_name: settings.groupName,
    };
    await saveUserState(userId, STEPS.DAY, initialData);

    const label = groupLabel(settings);
    const prompt = getStepPrompt(STEPS.DAY, initialData, label);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  // 10. Добавление урока: выбор дня
  if (callbackData.startsWith('day_')) {
    const day = parseInt(callbackData.replace('day_', ''), 10);
    const userState = await getUserState(userId);
    const data = userState?.data || {};
    data.day = day;

    await saveUserState(userId, STEPS.TIME, data);
    const settings = await getUserSettings(userId);
    const label = groupLabel(settings);

    const prompt = getStepPrompt(STEPS.TIME, data, label);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  // 11. Отмена в визарде -> главное меню
  if (callbackData === 'cancel_to_menu') {
    await clearUserState(userId);
    const settings = await getUserSettings(userId);
    const label = groupLabel(settings);
    await editOrSend(query, {
      text: settings ? `🎵 <b>Гнесинка</b> | ${label}\n\nЧто показать?` : '🏠 Главное меню',
      reply_markup: settings ? kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, settings.scheduleFormat) : kbEduLevels(),
    });
    return;
  }

  // 12. Навигация назад в визарде
  if (callbackData === 'nav_back') {
    const userState = await getUserState(userId);
    if (!userState) return;

    const data = userState.data || {};
    const settings = await getUserSettings(userId);
    const label = groupLabel(settings);

    let prevStep = STEPS.DAY;
    if (userState.step === STEPS.TIME) prevStep = STEPS.DAY;
    else if (userState.step === STEPS.TIME_END) prevStep = STEPS.TIME;
    else if (userState.step === STEPS.SUBJECT) prevStep = STEPS.TIME_END;
    else if (userState.step === STEPS.TEACHER) prevStep = STEPS.SUBJECT;
    else if (userState.step === STEPS.ROOM) prevStep = STEPS.TEACHER;
    else if (userState.step === STEPS.CONFIRM) prevStep = STEPS.ROOM;

    await saveUserState(userId, prevStep, data);
    const prompt = getStepPrompt(prevStep, data, label);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  // 13. Пропуск необязательного поля в визарде
  if (callbackData === 'skip') {
    const userState = await getUserState(userId);
    if (!userState) return;

    const data = userState.data || {};
    const settings = await getUserSettings(userId);
    const label = groupLabel(settings);

    let nextStep = userState.step;
    if (userState.step === STEPS.TIME_END) {
      data.time_end = null;
      nextStep = STEPS.SUBJECT;
    } else if (userState.step === STEPS.TEACHER) {
      data.teacher = null;
      nextStep = STEPS.ROOM;
    } else if (userState.step === STEPS.ROOM) {
      data.room = null;
      nextStep = STEPS.CONFIRM;
    }

    await saveUserState(userId, nextStep, data);
    const prompt = getStepPrompt(nextStep, data, label);
    await api.editMessageText({
      chat_id: chatId,
      message_id: messageId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  // 14. Сохранение урока
  if (callbackData === 'confirm') {
    const userState = await getUserState(userId);
    if (userState && userState.data) {
      await finalizeLesson(userId, userState.data);
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        text: '✅ Личный урок сохранён!',
        reply_markup: kbBack(),
        parse_mode: 'HTML',
      });
    }
    return;
  }
}
