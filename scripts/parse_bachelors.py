#!/usr/bin/env python3
import re
import json
import urllib.request
import subprocess
import os

HTML_PATH = "/home/ernes/.gemini/antigravity/brain/257291ab-a7b0-45f3-8ae5-13f9aab01919/.system_generated/steps/599/content.md"
PDF_DIR = "/home/ernes/gnes-project/data/academy_bachelor_pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

with open(HTML_PATH, "r", encoding="utf-8") as f:
    text = f.read()

lines = [l.strip() for l in text.split("\n") if l.strip()]
profiles = []
current_code = None
current_prog = None

for idx, l in enumerate(lines):
    if ".pdf" in l:
        profile = None
        for back in range(idx-1, max(0, idx-30), -1):
            s = re.sub(r"<[^>]+>", "", lines[back]).strip()
            if not s or "полугодие" in s.lower():
                continue
            if re.match(r"^\d{2}\.\d{2}\.\d{2}", s):
                current_code = s
            elif not profile and not s.startswith("<a"):
                profile = s
            elif not current_prog and not s.startswith("<a") and s != profile:
                current_prog = s

        m_pdf = re.search(r'href="([^"]+\.pdf)"', l)
        pdf = m_pdf.group(1) if m_pdf else ""
        if not pdf.startswith("http"):
            pdf = "https://gnesin-academy.ru" + pdf

        filename = pdf.split("/")[-1].replace(".pdf", "").replace("25_26_b_", "").replace("_1_", "")
        profiles.append({
            "id": f"bac_{filename}",
            "level": "bachelor",
            "code": current_code,
            "program": current_prog,
            "name": profile,
            "pdf": pdf,
            "groups": ["1 курс", "2 курс", "3 курс", "4 курс"]
        })

print(f"Extracted {len(profiles)} bachelor profiles.")

# Download each PDF and parse into structured schedule
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
DAYS_NORM = {
    "понедельник": "Понедельник",
    "вторник": "Вторник",
    "среда": "Среда",
    "четверг": "Четверг",
    "пятница": "Пятница",
    "суббота": "Суббота",
}
course_names = ["1 курс", "2 курс", "3 курс", "4 курс"]
col_ranges = [(10, 48), (48, 90), (90, 132), (132, 185)]

headers = {"User-Agent": "Mozilla/5.0"}
bachelor_schedules = {}

for p in profiles:
    p_id = p["id"]
    pdf_url = p["pdf"]
    pdf_path = os.path.join(PDF_DIR, f"{p_id}.pdf")

    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1000:
        print(f"Downloading {p['name']} from {pdf_url}...")
        try:
            req = urllib.request.Request(pdf_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(pdf_path, "wb") as out_f:
                    out_f.write(resp.read())
        except Exception as e:
            print(f"Failed to download {pdf_url}: {e}")
            continue

    # pdftotext
    try:
        raw_text = subprocess.check_output(["pdftotext", "-layout", pdf_path, "-"]).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Failed to pdftotext {pdf_path}: {e}")
        continue

    pages = raw_text.split("\x0c")
    parsed_sched = {c: {d: [] for d in DAYS_NORM.values()} for c in course_names}
    current_day = None

    for page in pages:
        for line in page.split("\n"):
            if "перечень индивидуальных дисциплин" in line.lower():
                break
            line_prefix = line[:25].lower()
            for d in DAYS:
                if d in line_prefix:
                    current_day = DAYS_NORM[d]
                    break
            if not current_day:
                continue

            for idx, (c_start, c_end) in enumerate(col_ranges):
                chunk = line[c_start:min(len(line), c_end)].rstrip()
                if not chunk.strip():
                    continue
                c_name = course_names[idx]
                m = re.search(r"(\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})", chunk)
                if m:
                    time_str = m.group(1).replace(" ", "")
                    rest = chunk[m.end():].strip()
                    parsed_sched[c_name][current_day].append({
                        "time": time_str,
                        "raw": [rest] if rest else []
                    })
                else:
                    if parsed_sched[c_name][current_day]:
                        parsed_sched[c_name][current_day][-1]["raw"].append(chunk.strip())

    # Format clean lessons
    clean_sched = {}
    for c_name in course_names:
        clean_sched[c_name] = {}
        for d_name, lessons in parsed_sched[c_name].items():
            day_lessons = []
            for l in lessons:
                full_text = " ".join(l["raw"]).strip()
                room = ""
                m_room = re.search(r"(?:кл\.|ауд\.)\s*([0-9a-zA-Zа-яА-ЯёЁ\-_]+(?:\s*\([^\)]+\))?)", full_text)
                if m_room:
                    room = m_room.group(0).strip()
                    full_text = full_text[:m_room.start()] + full_text[m_room.end():]
                elif "спортзал" in full_text.lower():
                    room = "Спортзал"
                elif "яндекс телемост" in full_text.lower():
                    room = "Яндекс Телемост"

                teacher = ""
                m_teach = re.search(r"пед\.\s*([А-Яа-яЁёA-Za-z\.\s]+?)(?=\s*(?:кл\.|ауд\.|гр\.|\(|$))", full_text)
                if m_teach:
                    teacher = m_teach.group(1).strip()
                    full_text = full_text[:m_teach.start()] + full_text[m_teach.end():]

                subject = re.sub(r"\s+", " ", full_text).strip(" ,.-")
                day_lessons.append({
                    "time": l["time"],
                    "subject": subject,
                    "teacher": teacher,
                    "room": room,
                })
            clean_sched[c_name][d_name] = day_lessons

    bachelor_schedules[p_id] = {
        "dept_name": p["name"],
        "code": p["code"],
        "program": p["program"],
        "pdf": p["pdf"],
        "groups": course_names,
        "schedule": clean_sched
    }

print(f"Successfully processed {len(bachelor_schedules)} bachelor schedules.")

with open("/home/ernes/gnes-project/data/bachelor_schedules.json", "w", encoding="utf-8") as f:
    json.dump(bachelor_schedules, f, ensure_ascii=False, indent=2)

print("Saved data/bachelor_schedules.json successfully.")
