/**
 * Endpoint для Telegram Mini App: сохранение фильтров (подгруппа, финансирование).
 */
import { updateUserFilters } from '../lib/user.js';

export default async function (input, ctx) {
  const userId = ctx?.initData?.user?.id || input?.userId;

  if (!userId) {
    return {
      ok: false,
      error: 'NO_USER_ID',
      message: 'Не удалось определить пользователя Telegram.',
    };
  }

  const { subgroup, funding } = input || {};
  await updateUserFilters(userId, subgroup, funding);

  return {
    ok: true,
    subgroup: subgroup || null,
    funding: funding || null,
  };
}
