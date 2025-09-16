from __future__ import annotations
from bs4 import BeautifulSoup
from datetime import datetime, time
from pathlib import Path
from typing import List
from .models import Course

DAY_MAP = {
    'Δευτέρα': 'Monday',
    'Τρίτη': 'Tuesday',
    'Τετάρτη': 'Wednesday',
    'Πέμπτη': 'Thursday',
    'Παρασκευή': 'Friday'
}

TIME_SEP = '–'  # en dash in source


def parse_time_range(s: str) -> tuple[time, time]:
    # Expect format HH:MM – HH:MM (with en dash or hyphen)
    if '–' in s:
        parts = [p.strip() for p in s.split('–')]
    else:
        parts = [p.strip() for p in s.split('-')]
    if len(parts) != 2:
        raise ValueError(f"Unrecognized time range: {s}")
    fmt = '%H:%M'
    start_dt = datetime.strptime(parts[0], fmt)
    end_dt = datetime.strptime(parts[1], fmt)
    return start_dt.time(), end_dt.time()


def _build_soup(html_text: str) -> BeautifulSoup:
    """Create a BeautifulSoup object without requiring external parsers.
    Try fast/best available built-ins; fall back gracefully.
    """
    for parser in ('html.parser', 'html5lib'):  # html5lib only if installed
        try:
            return BeautifulSoup(html_text, parser)
        except Exception:
            continue
    # last resort use default
    return BeautifulSoup(html_text, 'html.parser')


def parse_programme_html(html_text: str) -> List[Course]:
    soup = _build_soup(html_text)
    all_courses: List[Course] = []
    cid = 1
    # Each tab div id= tabs-1-<n>
    for tab in soup.select('div.tab_content'):
        # Day name from corresponding <a> by aria-labelledby
        label_id = tab.get('aria-labelledby')
        day_name_el = soup.select_one(f'a#{label_id}') if label_id else None
        greek_day = day_name_el.get_text(strip=True) if day_name_el else ''
        day = DAY_MAP.get(greek_day, greek_day)
        rows = tab.select('table.courses_timetable tr.sbody')
        for tr in rows:
            tds = tr.find_all('td')
            if len(tds) < 5:
                continue
            time_range = tds[0].get_text(strip=True)
            try:
                start, end = parse_time_range(time_range)
            except Exception:
                continue
            title_link = tds[1].find('a')
            title_el = title_link or tds[1]
            title = title_el.get_text(strip=True)
            url = title_link.get('href') if title_link else None
            kind = tds[2].get_text(strip=True)
            room = tds[3].get_text(strip=True)
            # Instructors: all li > a texts
            instructors = [a.get_text(strip=True) for a in tds[4].select('li a')] or [tds[4].get_text(strip=True)]
            course = Course(
                id=cid,
                title=title,
                day=day,
                start=start,
                end=end,
                kind=kind,
                room=room,
                instructors=instructors,
                original_html=str(tr),
                url=url
            )
            all_courses.append(course)
            cid += 1
    return all_courses


def load_from_file(path: Path) -> List[Course]:
    html_text = path.read_text(encoding='utf-8')
    return parse_programme_html(html_text)
