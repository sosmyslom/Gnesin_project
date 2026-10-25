import { dispatchAutoSchedules } from '../lib/auto_sender.js';

export default async function (input, ctx) {
  const customTime = input?.time || null;
  const result = await dispatchAutoSchedules(customTime);
  return result;
}
