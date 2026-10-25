#!/usr/bin/env python3
import json
import re

with open('public/data/schedules.json', 'r', encoding='utf-8') as f:
    existing_schedules = json.load(f)

with open('data/all_new_schedules.json', 'r', encoding='utf-8') as f:
    new_schedules = json.load(f)

# Clean IDs mapping
id_mapping = {
    'asp_5.8.7.-Raspisanie-zanyatiy-1-semestr-2026_2027': 'asp_5_8_7',
    'asp_5.10.3.-Raspisanie-zanyatiy-1-semestr-2026_2027': 'asp_5_10_3',
    'spec_s_p_2': 'spec_prod'
}

merged = {}

# 1. Add existing (SPO and Bachelor)
for k, v in existing_schedules.items():
    merged[k] = v

# 2. Add new schedules with cleaned IDs
for old_id, info in new_schedules.items():
    new_id = old_id
    if old_id in id_mapping:
        new_id = id_mapping[old_id]
    else:
        # Simplify redundant prefixes like mas_m_ -> mas_, spec_s_ -> spec_, as_as_st_ -> as_
        new_id = re.sub(r'^mas_m_', 'mas_', new_id)
        new_id = re.sub(r'^spec_s_', 'spec_', new_id)
        new_id = re.sub(r'^as_as_st_', 'as_', new_id)

    # Ensure groups are non-empty
    groups = info.get('groups', [])
    if not groups:
        groups = list(info.get('schedule', {}).keys())
    if not groups:
        groups = ['1 курс', '2 курс']
        
    merged[new_id] = {
        'dept_name': info['dept_name'],
        'level': info['level'],
        'pdf': info.get('pdf', ''),
        'groups': groups,
        'schedule': info['schedule']
    }

print(f"Total merged departments: {len(merged)}")
by_lvl = {}
for k, v in merged.items():
    by_lvl[v['level']] = by_lvl.get(v['level'], 0) + 1

for lvl, count in sorted(by_lvl.items()):
    print(f"  {lvl}: {count}")

with open('public/data/schedules.json', 'w', encoding='utf-8') as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

js_content = "/**\n * Расписания отделений всех уровней (СПО, Бакалавриат, Специалитет, Магистратура, Ассистентура, Аспирантура).\n */\n"
js_content += "export const DEFAULT_SCHEDULE = " + json.dumps(merged, ensure_ascii=False, indent=2) + ";\n"

with open('tgcloud/lib/default_schedule.js', 'w', encoding='utf-8') as f:
    f.write(js_content)

print("Saved public/data/schedules.json and tgcloud/lib/default_schedule.js successfully.")
