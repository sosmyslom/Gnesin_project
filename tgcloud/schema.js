import { table, integer, text, boolean, json, index, sql } from 'sdk/db';

export const userSettings = table('user_settings', {
  userId: integer('user_id').primaryKey(),
  deptId: text('dept_id').notNull(),
  deptName: text('dept_name').notNull(),
  groupName: text('group_name').notNull(),
  subgroup: text('subgroup'),
  funding: text('funding'),
  autoSchedule: boolean('auto_schedule').default(false),
  autoScheduleTime: text('auto_schedule_time').default('08:00'),
  scheduleFormat: text('schedule_format').default('text'),
  lastAutoDate: text('last_auto_date'),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
});

export const personalLessons = table('personal_lessons', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  userId: integer('user_id').notNull(),
  deptId: text('dept_id'),
  groupName: text('group_name'),
  dayOfWeek: integer('day_of_week').notNull(),
  timeStart: text('time_start').notNull(),
  timeEnd: text('time_end'),
  subject: text('subject').notNull(),
  teacher: text('teacher'),
  room: text('room'),
  createdAt: integer('created_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
}, (t) => ({
  userIdx: index('idx_lessons_user').on(t.userId),
}));

export const userStates = table('user_states', {
  userId: integer('user_id').primaryKey(),
  step: text('step').notNull(),
  data: json('data').notNull(),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
});

export const scheduleCache = table('schedule_cache', {
  deptId: text('dept_id').primaryKey(),
  deptName: text('dept_name').notNull(),
  groups: json('groups').notNull(),
  schedule: json('schedule').notNull(),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
});
