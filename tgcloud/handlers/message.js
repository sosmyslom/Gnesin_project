import { api } from 'sdk';
import { getUserSettings, groupLabel, getPersonalLessons, updateAutoScheduleTime } from '../lib/user.js';
import {
  kbMainMenu,
  kbEduLevels,
  kbDepartments,
  kbBack,
  kbStepNav,
  kbReplyKeyboard,
  kbDatePicker,
  kbPhotoDatePicker,
  kbPhotoMenu,
  kbSettingsMenu,
  kbAutoScheduleMenu,
  kbAutoTimeInput,
} from '../lib/keyboards.js';
import { formatPersonalLessons } from '../lib/formatter.js';
import {
  STEPS,
  parseValidTime,
  parseDateOrDay,
  getUserState,
  saveUserState,
  clearUserState,
  getStepPrompt,
} from '../lib/wizard.js';
import { sendPhotoSchedule } from '../lib/schedule_sender.js';

export default async function (message, ctx) {
  if (!message || !message.text) return;

  const chatId = message.chat.id;
  const userId = message.from.id;
  const text = message.text.trim();

  // 1. Команды
  if (text.startsWith('/')) {
    const cmd = text.split(/\s+/)[0].toLowerCase().split('@')[0];

    if (cmd === '/start') {
      await clearUserState(userId);
      const settings = await getUserSettings(userId);
      if (settings) {
        const label = groupLabel(settings);
        await api.sendMessage({
          chat_id: chatId,
          text: `🎵 <b>Гнесинка</b> | ${label}\n\nКнопки быстрого доступа закреплены внизу экрана ⬇️`,
          reply_markup: kbReplyKeyboard(),
          parse_mode: 'HTML',
        });
        await api.sendMessage({
          chat_id: chatId,
          text: 'Быстрый доступ к расписанию:',
          reply_markup: kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, settings.scheduleFormat),
          parse_mode: 'HTML',
        });
      } else {
        await api.sendMessage({
          chat_id: chatId,
          text:
            '🎵 <b>Добро пожаловать!</b>\n\n' +
            'Бот расписания Гнесинки (Училище и Академия).\n\n' +
            'Кнопки меню закреплены внизу экрана ⬇️',
          reply_markup: kbReplyKeyboard(),
          parse_mode: 'HTML',
        });
        await api.sendMessage({
          chat_id: chatId,
          text:
            '🎓 <b>Выберите ступень образования:</b>\n\n' +
            '• <b>СПО</b> — Музыкальное училище имени Гнесиных\n' +
            '• <b>Бакалавриат, Специалитет, Магистратура</b> (РАМ)',
          reply_markup: kbEduLevels(),
          parse_mode: 'HTML',
        });
      }
      return;
    }

    if (cmd === '/help') {
      await api.sendMessage({
        chat_id: chatId,
        text:
          '📖 <b>Команды бота</b>\n\n' +
          '/start — Главное меню / Настройка курса\n' +
          '/schedule — Выбор периода расписания\n' +
          '/add — Добавить личный урок\n' +
          '/my — Мои личные уроки\n' +
          '/help — Справка',
        reply_markup: kbReplyKeyboard(),
        parse_mode: 'HTML',
      });
      return;
    }

    if (cmd === '/schedule') {
      const settings = await getUserSettings(userId);
      if (!settings) {
        await api.sendMessage({
          chat_id: chatId,
          text: '⚠️ Сначала настройте группу: /start',
          reply_markup: kbReplyKeyboard(),
        });
        return;
      }
      const label = groupLabel(settings);
      await api.sendMessage({
        chat_id: chatId,
        text: `🎵 <b>${label}</b>\n\nВыберите период:`,
        reply_markup: kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, settings.scheduleFormat),
        parse_mode: 'HTML',
      });
      return;
    }

    if (cmd === '/add') {
      const settings = await getUserSettings(userId);
      if (!settings) {
        await api.sendMessage({
          chat_id: chatId,
          text: '⚠️ Сначала выберите отделение и курс в меню /start!',
          reply_markup: kbBack(),
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
      await api.sendMessage({
        chat_id: chatId,
        text: prompt.text,
        reply_markup: prompt.reply_markup,
        parse_mode: 'HTML',
      });
      return;
    }

    if (cmd === '/my') {
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

      let formatted = formatPersonalLessons(lessons);
      if (header && lessons && lessons.length > 0) {
        formatted = header + formatted.split('\n').slice(1).join('\n');
      }

      await api.sendMessage({
        chat_id: chatId,
        text: formatted,
        reply_markup: kbBack(),
        parse_mode: 'HTML',
      });
      return;
    }

    if (cmd === '/cancel') {
      await clearUserState(userId);
      const settings = await getUserSettings(userId);
      const label = groupLabel(settings);
      await api.sendMessage({
        chat_id: chatId,
        text: settings ? `🎵 <b>Гнесинка</b> | ${label}\n\nЧто показать?` : '🏠 Главное меню',
        reply_markup: settings ? kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, settings.scheduleFormat) : kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }
  }

  // 2. Обработка кнопок нижней клавиатуры (ReplyKeyboardMarkup)
  if (text === '⏱ Расписание' || text.toLowerCase() === 'расписание') {
    await clearUserState(userId);
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.sendMessage({
        chat_id: chatId,
        text:
          '🎓 <b>Выберите ступень образования:</b>\n\n' +
          '• <b>СПО</b> — Музыкальное училище имени Гнесиных\n' +
          '• <b>Бакалавриат, Специалитет, Магистратура</b> (РАМ)',
        reply_markup: kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }
    const label = groupLabel(settings);
    await api.sendMessage({
      chat_id: chatId,
      text: `🎵 <b>Гнесинка</b> | ${label}\n\nВыберите вариант расписания:`,
      reply_markup: kbMainMenu(userId, settings.autoSchedule, settings.autoScheduleTime, settings.scheduleFormat),
      parse_mode: 'HTML',
    });
    return;
  }

  if (text === '⏱ На дату' || text.toLowerCase() === 'на дату') {
    await clearUserState(userId);
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.sendMessage({
        chat_id: chatId,
        text:
          '🎓 <b>Выберите ступень образования:</b>\n\n' +
          '• <b>СПО</b> — Музыкальное училище имени Гнесиных\n' +
          '• <b>Бакалавриат, Специалитет, Магистратура</b> (РАМ)',
        reply_markup: kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }
    const label = groupLabel(settings);
    const isPhoto = settings.scheduleFormat === 'photo';
    if (isPhoto) {
      await api.sendMessage({
        chat_id: chatId,
        text: `📸 <b>Расписание по фото на день</b> | <i>${label}</i>\n\nВыберите нужный день недели:`,
        reply_markup: kbPhotoDatePicker(),
        parse_mode: 'HTML',
      });
    } else {
      await api.sendMessage({
        chat_id: chatId,
        text: `📆 <b>Расписание на день</b> (${label})\n\nВыберите день недели:`,
        reply_markup: kbDatePicker(false),
        parse_mode: 'HTML',
      });
    }
    return;
  }

  if (text === '💼 Настройки' || text.toLowerCase() === 'настройки') {
    await clearUserState(userId);
    const settings = await getUserSettings(userId);
    const label = settings ? groupLabel(settings) : 'Не выбрана';
    await api.sendMessage({
      chat_id: chatId,
      text:
        `💼 <b>Настройки профиля</b>\n\n` +
        `🎓 Ваша группа: <b>${label}</b>\n\n` +
        `Здесь вы можете управлять своими личными уроками или сменить курс:`,
      reply_markup: kbSettingsMenu(),
      parse_mode: 'HTML',
    });
    return;
  }

  if (text === '🔄 Сменить группу' || text.toLowerCase().includes('сменить группу')) {
    await clearUserState(userId);
    await api.sendMessage({
      chat_id: chatId,
      text:
        '🔄 <b>Смена группы</b>\n\n' +
        '🎓 <b>Выберите ступень образования:</b>\n\n' +
        '• <b>СПО</b> — Музыкальное училище имени Гнесиных\n' +
        '• <b>Бакалавриат, Специалитет, Магистратура</b> (РАМ)',
      reply_markup: kbEduLevels(),
      parse_mode: 'HTML',
    });
    return;
  }

  // Быстрые текстовые запросы: "фото", "фото на завтра", "фото 28.10"
  const lower = text.toLowerCase().trim();
  if (lower.startsWith('фото') || lower.includes('по фото') || lower.includes('расписание фото')) {
    const settings = await getUserSettings(userId);
    if (!settings) {
      await api.sendMessage({
        chat_id: chatId,
        text: '🎓 Сначала выберите ступень образования и группу: /start',
        reply_markup: kbEduLevels(),
        parse_mode: 'HTML',
      });
      return;
    }
    const clean = lower
      .replace(/^расписание\s+по\s+фото\s*/, '')
      .replace(/^расписание\s+фото\s*/, '')
      .replace(/^фото\s+расписание\s*/, '')
      .replace(/^фото\s*/, '')
      .trim();

    if (!clean || clean === 'меню') {
      await api.sendMessage({
        chat_id: chatId,
        text: `📸 <b>Расписание по фото</b> | <i>${groupLabel(settings)}</i>\n\nВыберите вариант:`,
        reply_markup: kbPhotoMenu(),
        parse_mode: 'HTML',
      });
      return;
    }
    if (clean === 'неделя' || clean === 'на неделю') {
      await sendPhotoSchedule(settings, chatId, null, null);
      return;
    }
    const parsed = parseDateOrDay(clean);
    if (parsed) {
      await sendPhotoSchedule(settings, chatId, null, parsed.dayOfWeek, parsed.label);
      return;
    }
  }

  // 3. Обработка шагов визарда и ввода текста
  const userState = await getUserState(userId);
  if (!userState) return;

  const currentStep = userState.step;
  const data = userState.data || {};
  const settings = await getUserSettings(userId);
  const label = groupLabel(settings);

  if (currentStep === STEPS.AUTO_TIME) {
    const valid = parseValidTime(text);
    if (!valid) {
      await api.sendMessage({
        chat_id: chatId,
        text: '⚠️ Некорректный формат. Введите время в формате <b>ЧЧ:ММ</b> (например: <code>08:00</code>):',
        reply_markup: kbAutoTimeInput(),
        parse_mode: 'HTML',
      });
      return;
    }

    await updateAutoScheduleTime(userId, valid);
    await clearUserState(userId);

    await api.sendMessage({
      chat_id: chatId,
      text: `⏰ <b>Авторасписание</b>\n\nСтатус: 🔔 <b>Включено</b> (ежедневно в <b>${valid}</b>)`,
      reply_markup: kbAutoScheduleMenu(true, valid),
      parse_mode: 'HTML',
    });
    return;
  }

  if (currentStep === STEPS.TIME) {
    const valid = parseValidTime(text);
    if (!valid) {
      await api.sendMessage({
        chat_id: chatId,
        text: '⚠️ Некорректное время! Введите время в формате ЧЧ:ММ (часы от 00 до 23, минуты от 00 до 59, например: <b>14:30</b>):',
        reply_markup: kbStepNav(false),
        parse_mode: 'HTML',
      });
      return;
    }

    data.time_start = valid;
    await saveUserState(userId, STEPS.TIME_END, data);
    const prompt = getStepPrompt(STEPS.TIME_END, data, label);
    await api.sendMessage({
      chat_id: chatId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  if (currentStep === STEPS.TIME_END) {
    const valid = parseValidTime(text);
    if (!valid) {
      await api.sendMessage({
        chat_id: chatId,
        text: '⚠️ Некорректное время! Введите время в формате ЧЧ:ММ (часы от 00 до 23, минуты от 00 до 59, например: <b>16:00</b>) или нажмите «Пропустить»:',
        reply_markup: kbStepNav(true),
        parse_mode: 'HTML',
      });
      return;
    }

    if (valid <= data.time_start) {
      await api.sendMessage({
        chat_id: chatId,
        text: `⚠️ Время окончания (<b>${valid}</b>) должно быть позже времени начала (<b>${data.time_start}</b>)! Введите более позднее время или нажмите «Пропустить»:`,
        reply_markup: kbStepNav(true),
        parse_mode: 'HTML',
      });
      return;
    }

    data.time_end = valid;
    await saveUserState(userId, STEPS.SUBJECT, data);
    const prompt = getStepPrompt(STEPS.SUBJECT, data, label);
    await api.sendMessage({
      chat_id: chatId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  if (currentStep === STEPS.SUBJECT) {
    data.subject = text;
    await saveUserState(userId, STEPS.TEACHER, data);
    const prompt = getStepPrompt(STEPS.TEACHER, data, label);
    await api.sendMessage({
      chat_id: chatId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  if (currentStep === STEPS.TEACHER) {
    data.teacher = text;
    await saveUserState(userId, STEPS.ROOM, data);
    const prompt = getStepPrompt(STEPS.ROOM, data, label);
    await api.sendMessage({
      chat_id: chatId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }

  if (currentStep === STEPS.ROOM) {
    data.room = text;
    await saveUserState(userId, STEPS.CONFIRM, data);
    const prompt = getStepPrompt(STEPS.CONFIRM, data, label);
    await api.sendMessage({
      chat_id: chatId,
      text: prompt.text,
      reply_markup: prompt.reply_markup,
      parse_mode: 'HTML',
    });
    return;
  }
}
