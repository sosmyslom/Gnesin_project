#!/usr/bin/env python3
import os
import glob
import re
import json
import subprocess
import xml.etree.ElementTree as ET

DAYS_MAP = {
    'понедельник': 'Понедельник',
    'вторник': 'Вторник',
    'среда': 'Среда',
    'четверг': 'Четверг',
    'пятница': 'Пятница',
    'суббота': 'Суббота'
}

SHORT_DAYS_MAP = {
    'пн': 'Понедельник',
    'вт': 'Вторник',
    'ср': 'Среда',
    'чт': 'Четверг',
    'пт': 'Пятница',
    'сб': 'Суббота'
}

NORM_MAP = {
    'i': '1 курс', 'ii': '2 курс', 'iii': '3 курс', 'iv': '4 курс', 'v': '5 курс', 'vi': '6 курс',
    '1': '1 курс', '2': '2 курс', '3': '3 курс', '4': '4 курс', '5': '5 курс', '6': '6 курс'
}

def extract_room_and_teacher(raw_text):
    room = ''
    # Match: кл. / ауд. / каб. / к. / К. followed by number/letters/dots/slashes
    m_room = re.search(r'(?:кл\.|ауд\.|каб\.|[Кк]\.)\s*([0-9a-zA-Zа-яА-ЯёЁ\-_\./]+(?:\s*\([^\)]+\))?)', raw_text)
    if m_room:
        room = m_room.group(0).strip()
        raw_text = raw_text[:m_room.start()] + ' ' + raw_text[m_room.end():]
    elif re.search(r'спортзал|спортивный зал', raw_text, re.IGNORECASE):
        room = 'Спортзал'
        raw_text = re.sub(r'спортзал|спортивный зал(?:\s*училища)?', '', raw_text, flags=re.IGNORECASE)
    elif re.search(r'яндекс\s*телемост|телемост', raw_text, re.IGNORECASE):
        room = 'Яндекс Телемост'
        raw_text = re.sub(r'\(?\s*яндекс\s*телемост\s*\)?|\(?\s*телемост\s*\)?', '', raw_text, flags=re.IGNORECASE)

    teacher = ''
    m_teach = re.search(r'пед\.\s*([А-Яа-яЁёA-Za-z\.\s\-]+?)(?=\s*(?:кл\.|ауд\.|каб\.|[Кк]\.|гр\.|\(|$))', raw_text)
    if m_teach:
        teacher = m_teach.group(1).strip()
        raw_text = raw_text[:m_teach.start()] + ' ' + raw_text[m_teach.end():]
    else:
        m_fio = re.search(r'\b([А-ЯЁ][а-яё\-]+)\s+([А-ЯЁ]\.\s*[А-ЯЁ]\.)\b', raw_text)
        if m_fio:
            teacher = f'{m_fio.group(1)} {m_fio.group(2).replace(" ", "")}'
            raw_text = raw_text[:m_fio.start()] + ' ' + raw_text[m_fio.end():]

    if teacher:
        m_t_room = re.search(r'(?:кл\.|ауд\.|каб\.|[Кк]\.)\s*([0-9a-zA-Zа-яА-ЯёЁ\-_\./]+(?:\s*\([^\)]+\))?)', teacher)
        if m_t_room:
            if not room:
                room = m_t_room.group(0).strip()
            teacher = (teacher[:m_t_room.start()] + ' ' + teacher[m_t_room.end():]).strip()

    subject = re.sub(r'\s+', ' ', raw_text).strip(' ,.-/')
    # Clean room format
    if room:
        room = re.sub(r'^[Кк]\.\s*', 'кл.', room)
    return subject, teacher.strip(' ,.-/'), room.strip(' ,.-/')

def parse_pdf_bbox(pdf_path):
    try:
        xml_data = subprocess.check_output(['pdftotext', '-bbox-layout', pdf_path, '-'])
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"Failed to pdftotext {pdf_path}: {e}")
        return None, []
        
    # 1. Course columns
    candidate_lines = []
    for line in root.iter('{http://www.w3.org/1999/xhtml}line'):
        yMin = float(line.attrib.get('yMin', 0))
        if yMin > 250:
            continue
        txt = ' '.join(w.text for w in line.iter('{http://www.w3.org/1999/xhtml}word') if w.text)
        m = re.search(r'\b(IV|VI|V|III|II|I|[1-6])\s*курс\b', txt, re.IGNORECASE)
        if m:
            c_num = m.group(1).lower()
            xMin = float(line.attrib.get('xMin', 0))
            candidate_lines.append((yMin, xMin, NORM_MAP.get(c_num, c_num)))
            
    if not candidate_lines:
        columns = [('1 курс', (50, 9999))]
    else:
        y_clusters = {}
        for y, x, name in candidate_lines:
            placed = False
            for cy in y_clusters:
                if abs(cy - y) < 15:
                    y_clusters[cy].append((x, name))
                    placed = True
                    break
            if not placed:
                y_clusters[y] = [(x, name)]
        best = max(y_clusters.values(), key=len)
        best.sort(key=lambda x: x[0])
        columns = []
        for i in range(len(best)):
            x_pos, c_name = best[i]
            left = 50 if i == 0 else (best[i-1][0] + x_pos) / 2
            right = (x_pos + best[i+1][0]) / 2 if i < len(best) - 1 else 9999
            columns.append((c_name, (left, right)))
            
    course_names = [c[0] for c in columns]
    sched = {c: {d: [] for d in DAYS_MAP.values()} for c in course_names}
    
    days_order = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']
    time_regex = re.compile(r'(\d{1,2}[:\.]\d{2}\s*[\-–—]\s*\d{1,2}[:\.]\d{2})')
    
    hit_global_footer = False
    
    for p_idx, page in enumerate(root.iter('{http://www.w3.org/1999/xhtml}page')):
        if hit_global_footer:
            break
            
        p_height = float(page.attrib.get('height', 600))
        footer_y = p_height
        
        # Check if page has footer (перечень индивидуальных дисциплин / практика / начальник УМО)
        for line in page.iter('{http://www.w3.org/1999/xhtml}line'):
            txt = ' '.join(w.text for w in line.iter('{http://www.w3.org/1999/xhtml}word') if w.text).lower()
            is_footer = False
            if 'перечень индивидуальных' in txt or 'перечень мелкогрупповых' in txt or 'перечень дисциплин' in txt:
                is_footer = True
            elif 'начальник учебно-методического' in txt or 'начальник умо' in txt:
                is_footer = True
            elif re.search(r'^\s*практика\s*$', txt):
                is_footer = True
            elif re.search(r'практика\s*[-–—]\s*\d+\s*ч', txt):
                is_footer = True
                
            # Must NOT be an actual lesson line with a scheduled time
            if is_footer and not time_regex.search(txt):
                yMin = float(line.attrib.get('yMin', p_height))
                if yMin > 180:
                    footer_y = min(footer_y, yMin)
                    hit_global_footer = True
                
        # Find days on this page with bounding boxes
        days_on_page = []
        for line in page.iter('{http://www.w3.org/1999/xhtml}line'):
            xMin = float(line.attrib.get('xMin', 999))
            if xMin < 220:
                for w in line.iter('{http://www.w3.org/1999/xhtml}word'):
                    t = w.text.lower() if w.text else ''
                    for d in days_order:
                        if d == t:
                            yMin = float(w.attrib.get('yMin', 0))
                            yMax = float(w.attrib.get('yMax', 0))
                            days_on_page.append((DAYS_MAP[d], yMin, yMax))
                            
        # Fallback to short day names (пн, вт, ср, чт, пт, сб) if full names not present
        if not days_on_page:
            for line in page.iter('{http://www.w3.org/1999/xhtml}line'):
                xMin = float(line.attrib.get('xMin', 999))
                if xMin < 220:
                    for w in line.iter('{http://www.w3.org/1999/xhtml}word'):
                        t = w.text.lower() if w.text else ''
                        if t in SHORT_DAYS_MAP:
                            yMin = float(w.attrib.get('yMin', 0))
                            yMax = float(w.attrib.get('yMax', 0))
                            days_on_page.append((SHORT_DAYS_MAP[t], yMin, yMax))

        days_on_page.sort(key=lambda x: x[1])
        
        if not days_on_page:
            continue
            
        # Build midpoint vertical ranges for days
        day_ranges = []
        for i in range(len(days_on_page)):
            d_name, y_w_min, y_w_max = days_on_page[i]
            start = (150 if p_idx == 0 else 40) if i == 0 else (days_on_page[i-1][2] + y_w_min) / 2
            end = (y_w_max + days_on_page[i+1][1]) / 2 if i < len(days_on_page) - 1 else footer_y
            day_ranges.append((d_name, start, end))
            
        # Collect lines on this page above footer
        page_lines = []
        for line in page.iter('{http://www.w3.org/1999/xhtml}line'):
            xMin = float(line.attrib.get('xMin', 0))
            yMin = float(line.attrib.get('yMin', 0))
            txt = ' '.join(w.text for w in line.iter('{http://www.w3.org/1999/xhtml}word') if w.text).strip()
            # Filter out day names in left column and left margin
            txt_clean = txt.lower().strip(' ,.-/')
            is_day_label = (txt_clean in days_order and xMin < 75) or (txt_clean in SHORT_DAYS_MAP and xMin < 75) or xMin < 50
            if is_day_label:
                continue
            if txt and yMin < footer_y:
                page_lines.append((yMin, xMin, txt))
                
        page_lines.sort(key=lambda x: (x[0], x[1]))
        
        for yMin, xMin, txt in page_lines:
            target_day = None
            for d_name, y1, y2 in day_ranges:
                if y1 <= yMin < y2:
                    target_day = d_name
                    break
            if not target_day:
                continue
                
            target_course = None
            for c_name, (x1, x2) in columns:
                if x1 <= xMin < x2:
                    target_course = c_name
                    break
            if not target_course:
                continue
                
            # Filter out any footer keywords if somehow inside day
            txt_lower = txt.lower()
            if any(k in txt_lower for k in ['перечень индивидуальных', 'специальный инструмент -', 'дирижирование - 34', 'практика - 9 ч', 'практика - 17 ч']):
                continue
                
            m_time = time_regex.search(txt)
            if m_time:
                t_raw = m_time.group(1)
                t_norm = re.sub(r'\s+', '', t_raw).replace('.', ':').replace('–', '-').replace('—', '-')
                rest = (txt[:m_time.start()] + ' ' + txt[m_time.end():]).strip()
                sched[target_course][target_day].append({
                    'time': t_norm,
                    'raw': [rest] if rest else []
                })
            else:
                if sched[target_course][target_day]:
                    # Ignore pure hours strings
                    if not re.search(r'^\s*[-–—]?\s*\d+\s*ч\.?\s*$', txt) and not re.search(r'\b\d+\s*ч\b', txt):
                        sched[target_course][target_day][-1]['raw'].append(txt)
                        
    # Format and clean lessons
    clean_sched = {}
    for c_name in course_names:
        clean_sched[c_name] = {}
        for d_name, lessons in sched[c_name].items():
            day_lessons = []
            for l in lessons:
                full_text = ' '.join(l['raw']).strip()
                subj, teach, rm = extract_room_and_teacher(full_text)
                for d_word in ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']:
                    subj = re.sub(rf'\b{d_word}\b', '', subj, flags=re.IGNORECASE)
                subj = re.sub(r'\s+', ' ', subj).strip(' ,.-/')
                day_lessons.append({
                    'time': l['time'],
                    'subject': subj,
                    'teacher': teach,
                    'room': rm
                })
            clean_sched[c_name][d_name] = day_lessons
            
    return clean_sched, course_names

def main():
    with open('public/data/schedules.json', 'r', encoding='utf-8') as f:
        existing_schedules = json.load(f)

    if os.path.exists('data/all_new_schedules.json'):
        with open('data/all_new_schedules.json', 'r', encoding='utf-8') as f:
            all_new = json.load(f)
            for k, v in all_new.items():
                if k not in existing_schedules:
                    existing_schedules[k] = v

    # 1. Clean SPO college lessons (e.g. Захаренкова Н.В. К.32)
    cleaned_count = 0
    for dept_id in ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10']:
        if dept_id in existing_schedules:
            for grp, days in existing_schedules[dept_id].get('schedule', {}).items():
                for d, lessons in days.items():
                    for l in lessons:
                        t = l.get('teacher', '')
                        r = l.get('room', '')
                        m = re.search(r'[Кк]\.?\s*(\d+[a-zA-Zа-яА-ЯёЁ\-_/]*)', t)
                        if m:
                            if not r:
                                l['room'] = m.group(1)
                            l['teacher'] = re.sub(r'\s*[Кк]\.?\s*\d+[a-zA-Zа-яА-ЯёЁ\-_/]*', '', t).strip(' ,.-/')
                            cleaned_count += 1
    print(f"Cleaned {cleaned_count} SPO room tags from teachers.")

    # 2. Re-parse all Academy PDFs
    reparsed_schedules = {}
    for dept_id, info in existing_schedules.items():
        if info['level'] == 'spo':
            reparsed_schedules[dept_id] = info
            continue
            
        lvl = info['level']
        pdf_path = None
        
        if lvl == 'bachelor':
            p = f'data/academy_bachelor_pdfs/{dept_id}.pdf'
            if os.path.exists(p):
                pdf_path = p
        elif lvl == 'master':
            suffix = dept_id.replace('mas_', '')
            p = f'data/academy_master_pdfs/mas_m_{suffix}.pdf'
            if os.path.exists(p):
                pdf_path = p
        elif lvl == 'specialist':
            suffix = dept_id.replace('spec_', '')
            if dept_id == 'spec_prod':
                p = 'data/academy_specialty_pdfs/spec_s_p.pdf'
            elif dept_id == 'spec_p':
                p = 'data/academy_specialty_pdfs/spec_s_fp.pdf'
            else:
                p = f'data/academy_specialty_pdfs/spec_s_{suffix}.pdf'
            if os.path.exists(p):
                pdf_path = p

        if not pdf_path:
            # Check by pdf field
            pdf_url = info.get('pdf', '')
            fname = pdf_url.split('/')[-1]
            for p in glob.glob(f'data/*/{fname}'):
                if os.path.exists(p):
                    pdf_path = p
                    break
                
        if not pdf_path:
            print(f"Warning: PDF not found for {dept_id} ({info['dept_name']}), keeping existing.")
            reparsed_schedules[dept_id] = info
            continue
            
        new_sched, groups = parse_pdf_bbox(pdf_path)
        if not new_sched:
            print(f"Warning: bbox parse failed for {dept_id}, keeping existing.")
            reparsed_schedules[dept_id] = info
            continue
            
        all_groups = []
        for g in (groups if groups else []):
            if g not in all_groups:
                all_groups.append(g)
        for g in info.get('groups', []):
            if g not in all_groups:
                all_groups.append(g)
        if not all_groups:
            all_groups = ['1 курс', '2 курс']

        for g in all_groups:
            if g not in new_sched:
                new_sched[g] = {d: [] for d in DAYS_MAP.values()}

        pdf_url = info.get('pdf', '')
        if dept_id == 'spec_p':
            pdf_url = 'https://gnesin-academy.ru/upload/iblock/9d1/fgb3y10ibkyjqmv2v17tjhg0o1ezpigc/25_26_s_fp_1_.pdf'

        reparsed_schedules[dept_id] = {
            'dept_name': info['dept_name'],
            'level': info['level'],
            'pdf': pdf_url,
            'groups': all_groups,
            'schedule': new_sched
        }
        
    print(f"Successfully processed {len(reparsed_schedules)} departments.")
    
    # Verify no leaks
    leak_count = 0
    for dept_id, info in reparsed_schedules.items():
        for grp, days in info.get('schedule', {}).items():
            for d, lessons in days.items():
                for l in lessons:
                    txt = (l.get('subject', '') + ' ' + l.get('teacher', '')).lower()
                    if any(k in txt for k in ['перечень индивидуальных', 'специальный инструмент -', 'практика - 9 ч', ' - 17 ч', ' - 34 ч']):
                        leak_count += 1
                        print(f"STILL LEAKED in {dept_id} ({info['dept_name']}): {l['subject'][:60]}")
                        
    print(f"Leak verification: {leak_count} leaks remaining.")
    
    with open('public/data/schedules.json', 'w', encoding='utf-8') as f:
        json.dump(reparsed_schedules, f, ensure_ascii=False, indent=2)
        
    js_content = "/**\n * Расписания отделений всех уровней (СПО, Бакалавриат, Специалитет, Магистратура, Ассистентура, Аспирантура).\n */\n"
    js_content += "export const DEFAULT_SCHEDULE = " + json.dumps(reparsed_schedules, ensure_ascii=False, indent=2) + ";\n"
    js_content += "export const defaultSchedule = DEFAULT_SCHEDULE;\nexport default DEFAULT_SCHEDULE;\n"
    
    with open('tgcloud/lib/default_schedule.js', 'w', encoding='utf-8') as f:
        f.write(js_content)
        
    print("Saved public/data/schedules.json and tgcloud/lib/default_schedule.js successfully.")

if __name__ == '__main__':
    main()
