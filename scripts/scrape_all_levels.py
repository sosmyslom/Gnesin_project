#!/usr/bin/env python3
import os
import re
import json
import urllib.request
import subprocess

PAGES = [
    {
        'level': 'master',
        'level_title': 'Магистратура',
        'prefix': 'mas',
        'url': 'https://gnesin-academy.ru/for-students/classes-timetable/masters-degree/',
        'pdf_dir': '/home/ernes/gnes-project/data/academy_master_pdfs'
    },
    {
        'level': 'specialist',
        'level_title': 'Специалитет',
        'prefix': 'spec',
        'url': 'https://gnesin-academy.ru/for-students/classes-timetable/specialty/',
        'pdf_dir': '/home/ernes/gnes-project/data/academy_specialty_pdfs'
    },
    {
        'level': 'assistantship',
        'level_title': 'Ассистентура-стажировка',
        'prefix': 'as',
        'url': 'https://gnesin-academy.ru/for-students/classes-timetable/assistantship-internship/',
        'pdf_dir': '/home/ernes/gnes-project/data/academy_assistantship_pdfs'
    },
    {
        'level': 'postgraduate',
        'level_title': 'Аспирантура',
        'prefix': 'asp',
        'url': 'https://gnesin-academy.ru/for-students/classes-timetable/postgraduate-studies/',
        'pdf_dir': '/home/ernes/gnes-project/data/academy_postgraduate_pdfs'
    }
]

DAYS = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']
DAYS_NORM = {
    'понедельник': 'Понедельник',
    'вторник': 'Вторник',
    'среда': 'Среда',
    'четверг': 'Четверг',
    'пятница': 'Пятница',
    'суббота': 'Суббота'
}

NORM_MAP = {
    'i': '1 курс', 'ii': '2 курс', 'iii': '3 курс', 'iv': '4 курс', 'v': '5 курс', 'vi': '6 курс',
    '1': '1 курс', '2': '2 курс', '3': '3 курс', '4': '4 курс', '5': '5 курс', '6': '6 курс'
}

HEADERS = {'User-Agent': 'Mozilla/5.0'}

def extract_profiles_from_html(html, level_info):
    profiles = []
    # Search for student-schedule-item-program
    matches = list(re.finditer(r'<div class=\"student-schedule-item-program__name\">([^<]+)</div>\s*<div class=\"student-schedule-item-program__lists\">.*?<a[^>]+href=[\"\']([^\"\']+\.pdf)[\"\'][^>]*>([^<]+)</a>', html, re.DOTALL))
    
    if matches:
        for m in matches:
            name = m.group(1).strip()
            pdf_rel = m.group(2).strip()
            pdf_url = pdf_rel if pdf_rel.startswith('http') else 'https://gnesin-academy.ru' + pdf_rel
            
            # create safe slug
            filename = pdf_url.split('/')[-1].replace('.pdf', '')
            filename = re.sub(r'^(25_26_|24_25_)', '', filename)
            filename = re.sub(r'(_1_|_2_)$', '', filename)
            
            p_id = f"{level_info['prefix']}_{filename}"
            profiles.append({
                'id': p_id,
                'name': name,
                'level': level_info['level'],
                'pdf': pdf_url
            })
    else:
        # Fallback for pages like postgraduate where markup may differ
        link_matches = list(re.finditer(r'<a[^>]+href=[\"\']([^\"\']+\.pdf)[\"\'][^>]*>(.*?)</a>', html, re.DOTALL))
        for idx, lm in enumerate(link_matches):
            pdf_rel = lm.group(1).strip()
            pdf_url = pdf_rel if pdf_rel.startswith('http') else 'https://gnesin-academy.ru' + pdf_rel
            raw_title = re.sub(r'<[^>]+>', '', lm.group(2)).strip()
            
            # find preceding header/text
            start_pos = max(0, lm.start() - 300)
            chunk = html[start_pos:lm.start()]
            name = None
            for line in reversed(chunk.split('\n')):
                clean = re.sub(r'<[^>]+>', '', line).strip()
                if clean and 'полугодие' not in clean.lower() and len(clean) > 5:
                    name = clean
                    break
            if not name or len(name) < 4:
                name = raw_title if len(raw_title) > 5 else f"Профиль {idx+1}"
                
            fname = pdf_url.split('/')[-1].replace('.pdf', '')
            fname = re.sub(r'[^a-zA-Z0-9_\-]', '_', fname)[:20]
            p_id = f"{level_info['prefix']}_{fname}"
            profiles.append({
                'id': p_id,
                'name': name,
                'level': level_info['level'],
                'pdf': pdf_url
            })
            
    # Deduplicate IDs if needed
    seen = {}
    unique_profiles = []
    for p in profiles:
        base_id = p['id']
        if base_id in seen:
            seen[base_id] += 1
            p['id'] = f"{base_id}_{seen[base_id]}"
        else:
            seen[base_id] = 1
        unique_profiles.append(p)
        
    return unique_profiles

def parse_header_columns(line):
    matches = list(re.finditer(r'(IV|VI|V|III|II|I|[1-6])\s*курс', line, re.IGNORECASE))
    if not matches:
        return None
    starts = [m.start() for m in matches]
    names = []
    for m in matches:
        k = re.search(r'(IV|VI|V|III|II|I|[1-6])', m.group(0), re.IGNORECASE).group(1).lower()
        names.append(NORM_MAP.get(k, m.group(0)))
        
    ranges = []
    for i in range(len(matches)):
        start = 10 if i == 0 else (starts[i-1] + starts[i]) // 2
        end = (starts[i] + starts[i+1]) // 2 if i < len(matches) - 1 else 9999
        ranges.append((names[i], (start, end)))
    return ranges

def parse_single_pdf(pdf_path, default_groups=None):
    try:
        raw_text = subprocess.check_output(['pdftotext', '-layout', pdf_path, '-']).decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Failed to pdftotext {pdf_path}: {e}")
        return None, []
        
    pages = raw_text.split('\x0c')
    
    # 1. Detect columns across all pages
    col_ranges = None
    for page in pages:
        for line in page.split('\n'):
            res = parse_header_columns(line)
            if res and len(res) > 0:
                col_ranges = res
                break
        if col_ranges:
            break
            
    if not col_ranges:
        # Check if single course mentioned in header, e.g. "2 курс"
        single_course = '1 курс'
        for page in pages:
            m = re.search(r'\b(IV|VI|V|III|II|I|[1-6])\s*курс\b', page, re.IGNORECASE)
            if m:
                k = m.group(1).lower()
                single_course = NORM_MAP.get(k, '1 курс')
                break
        col_ranges = [(single_course, (0, 9999))]

    course_names = [c[0] for c in col_ranges]
    parsed_sched = {c: {d: [] for d in DAYS_NORM.values()} for c in course_names}
    current_day = None
    
    time_regex = re.compile(r'(\d{1,2}[:\.]\d{2}\s*[\-–—]\s*\d{1,2}[:\.]\d{2})')
    
    for page in pages:
        for line in page.split('\n'):
            if 'перечень индивидуальных дисциплин' in line.lower():
                break
            line_prefix = line[:25].lower()
            for d in DAYS:
                if d in line_prefix:
                    current_day = DAYS_NORM[d]
                    break
            if not current_day:
                continue
                
            for c_name, (c_start, c_end) in col_ranges:
                chunk = line[c_start:min(len(line), c_end)].rstrip()
                if not chunk.strip():
                    continue
                m = time_regex.search(chunk)
                if m:
                    time_raw = m.group(1)
                    # normalize time to HH:MM-HH:MM
                    time_norm = re.sub(r'\s+', '', time_raw).replace('.', ':').replace('–', '-').replace('—', '-')
                    rest = chunk[m.end():].strip()
                    parsed_sched[c_name][current_day].append({
                        'time': time_norm,
                        'raw': [rest] if rest else []
                    })
                else:
                    if parsed_sched[c_name][current_day]:
                        parsed_sched[c_name][current_day][-1]['raw'].append(chunk.strip())
                        
    # Clean up lessons
    clean_sched = {}
    for c_name in course_names:
        clean_sched[c_name] = {}
        for d_name, lessons in parsed_sched[c_name].items():
            day_lessons = []
            for l in lessons:
                full_text = ' '.join(l['raw']).strip()
                
                room = ''
                m_room = re.search(r'(?:кл\.|ауд\.)\s*([0-9a-zA-Zа-яА-ЯёЁ\-_]+(?:\s*\([^\)]+\))?)', full_text)
                if m_room:
                    room = m_room.group(0).strip()
                    full_text = full_text[:m_room.start()] + full_text[m_room.end():]
                elif 'спортзал' in full_text.lower():
                    room = 'Спортзал'
                elif 'яндекс телемост' in full_text.lower() or 'телемост' in full_text.lower():
                    room = 'Яндекс Телемост'
                    
                teacher = ''
                m_teach = re.search(r'пед\.\s*([А-Яа-яЁёA-Za-z\.\s]+?)(?=\s*(?:кл\.|ауд\.|гр\.|\(|$))', full_text)
                if m_teach:
                    teacher = m_teach.group(1).strip()
                    full_text = full_text[:m_teach.start()] + full_text[m_teach.end():]
                    
                subject = re.sub(r'\s+', ' ', full_text).strip(' ,.-')
                day_lessons.append({
                    'time': l['time'],
                    'subject': subject,
                    'teacher': teacher,
                    'room': room
                })
            clean_sched[c_name][d_name] = day_lessons
            
    return clean_sched, course_names

def main():
    all_new_schedules = {}
    all_new_depts = {}
    
    for page in PAGES:
        lvl = page['level']
        print(f"\n================ PROCESSING LEVEL: {lvl.upper()} ================")
        os.makedirs(page['pdf_dir'], exist_ok=True)
        
        req = urllib.request.Request(page['url'], headers=HEADERS)
        html = urllib.request.urlopen(req).read().decode('utf-8')
        profiles = extract_profiles_from_html(html, page)
        print(f"Extracted {len(profiles)} profiles for {lvl}.")
        
        for p in profiles:
            p_id = p['id']
            pdf_url = p['pdf']
            pdf_name = pdf_url.split('/')[-1]
            pdf_path = os.path.join(page['pdf_dir'], f"{p_id}.pdf")
            
            if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1000:
                print(f"Downloading {p['name']} ({pdf_url})...")
                try:
                    req_pdf = urllib.request.Request(pdf_url, headers=HEADERS)
                    with urllib.request.urlopen(req_pdf, timeout=20) as resp:
                        with open(pdf_path, 'wb') as f:
                            f.write(resp.read())
                except Exception as e:
                    print(f"Failed to download {pdf_url}: {e}")
                    continue
                    
            clean_sched, course_names = parse_single_pdf(pdf_path)
            if not course_names:
                course_names = ['1 курс', '2 курс']
                
            all_new_schedules[p_id] = {
                'dept_name': p['name'],
                'level': lvl,
                'pdf': pdf_url,
                'groups': course_names,
                'schedule': clean_sched
            }
            
            all_new_depts[p_id] = {
                'level': lvl,
                'name': p['name']
            }
            
        print(f"Done level {lvl}: {len(profiles)} parsed.")
        
    print(f"\nTotal new schedules parsed: {len(all_new_schedules)}")
    with open('/home/ernes/gnes-project/data/all_new_schedules.json', 'w', encoding='utf-8') as f:
        json.dump(all_new_schedules, f, ensure_ascii=False, indent=2)
    print("Saved to data/all_new_schedules.json")

if __name__ == '__main__':
    main()
