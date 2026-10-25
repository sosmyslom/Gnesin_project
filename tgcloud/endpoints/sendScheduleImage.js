import { api, InputFile } from 'sdk';

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const B64_LOOKUP = new Uint8Array(256);
for (let i = 0; i < B64_CHARS.length; i++) {
  B64_LOOKUP[B64_CHARS.charCodeAt(i)] = i;
}

function base64ToUint8Array(base64) {
  const clean = base64.replace(/[^A-Za-z0-9+/]/g, '');
  const len = clean.length;
  if (len === 0) return new Uint8Array(0);
  const placeHolders = base64.endsWith('==') ? 2 : (base64.endsWith('=') ? 1 : 0);
  const bytesLen = Math.floor((len * 3) / 4) - placeHolders;
  const bytes = new Uint8Array(bytesLen);

  let curByte = 0;
  for (let i = 0; i < len; i += 4) {
    const enc1 = B64_LOOKUP[clean.charCodeAt(i)];
    const enc2 = B64_LOOKUP[clean.charCodeAt(i + 1)];
    const enc3 = B64_LOOKUP[clean.charCodeAt(i + 2)];
    const enc4 = B64_LOOKUP[clean.charCodeAt(i + 3)];

    bytes[curByte++] = (enc1 << 2) | (enc2 >> 4);
    if (curByte < bytesLen) bytes[curByte++] = ((enc2 & 15) << 4) | (enc3 >> 2);
    if (curByte < bytesLen) bytes[curByte++] = ((enc3 & 3) << 6) | (enc4 & 63);
  }
  return bytes;
}

export default async function (input, ctx) {
  const userId = ctx?.initData?.user?.id || input?.userId;
  if (!userId) {
    return { ok: false, error: 'NO_USER_ID', message: 'Не удалось определить пользователя.' };
  }

  const base64Data = input?.image;
  if (!base64Data) {
    return { ok: false, error: 'NO_IMAGE', message: 'Изображение не получено.' };
  }

  const match = base64Data.match(/^data:image\/\w+;base64,(.+)$/);
  const rawBase64 = match ? match[1] : base64Data;

  const bytes = base64ToUint8Array(rawBase64);
  const label = input.label || (input.deptName && input.groupName ? `${input.deptName} • ${input.groupName}` : 'Расписание');

  try {
    try {
      await api.sendDocument({
        chat_id: userId,
        document: new InputFile(bytes, 'schedule_week.png', { type: 'image/png' }),
        caption: `📅 <b>Ваше расписание на неделю</b>\n🎓 <i>${label}</i>`,
        parse_mode: 'HTML',
      });
    } catch (docErr) {
      console.warn('sendDocument failed, trying sendPhoto:', docErr?.message || docErr);
      await api.sendPhoto({
        chat_id: userId,
        photo: new InputFile(bytes, 'schedule_week.png', { type: 'image/png' }),
        caption: `📅 <b>Ваше расписание на неделю</b>\n🎓 <i>${label}</i>`,
        parse_mode: 'HTML',
      });
    }
  } catch (err) {
    console.error('Failed to send image to user chat:', err);
    return {
      ok: false,
      error: 'SEND_FAILED',
      message: 'Не удалось отправить картинку в чат: ' + (err?.description || err?.message || 'ошибка отправки'),
    };
  }

  return { ok: true, message: 'Расписание отправлено вам в чат!' };
}
