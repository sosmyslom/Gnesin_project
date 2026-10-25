/**
 * Endpoint для Telegram Mini App: возвращает расписание курса и личные уроки студента.
 */
import { getUserSettings, getPersonalLessons } from '../lib/user.js';
import { getScheduleForDept } from '../lib/schedule.js';

export default async function (input, ctx) {
  const userId = ctx?.initData?.user?.id || input?.userId;

  if (!userId) {
    return {
      ok: false,
      error: 'NO_USER_ID',
      message: 'Не удалось определить пользователя Telegram.',
    };
  }

  const settings = await getUserSettings(userId);
  if (!settings) {
    return {
      ok: true,
      found: false,
      message: 'Вы ещё не настроили группу в боте. Отправьте /start в чате с ботом.',
    };
  }

  const { schedule } = await getScheduleForDept(settings.deptId);
  const personal = await getPersonalLessons(userId, settings.deptId, settings.groupName);

  return {
    ok: true,
    found: true,
    user: {
      id: userId,
      deptId: settings.deptId,
      deptName: settings.deptName,
      groupName: settings.groupName,
      subgroup: settings.subgroup || null,
      funding: settings.funding || null,
    },
    groupSchedule: schedule[settings.groupName] || {},
    personalLessons: personal || [],
  };
}
