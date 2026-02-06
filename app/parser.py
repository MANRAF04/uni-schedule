from __future__ import annotations
from bs4 import BeautifulSoup
from datetime import datetime, time
from pathlib import Path
from urllib.request import Request, urlopen
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
    # Build mapping from tab content id -> day label (for pages that use tabs without aria-labelledby)
    tab_day_map: dict[str, str] = {}
    tabs_container = soup.select_one('div.tabs.tab-shortcode.office-tabs')
    if tabs_container:
        tabs_list = tabs_container.find('ul', class_='clearfix')
        if tabs_list:
            for a in tabs_list.select('li a[href]'):
                href = a.get('href', '')
                if href.startswith('#'):
                    tab_id = href.lstrip('#')
                    tab_day_map[tab_id] = a.get_text(strip=True)
    all_courses: List[Course] = []
    cid = 1
    # Each tab div id= tabs-1-<n>
    for tab in soup.select('div.tab_content'):
        tab_id = tab.get('id')
        tab_label = tab_day_map.get(tab_id, '') if tab_id else ''
        # Day name from corresponding <a> by aria-labelledby
        label_id = tab.get('aria-labelledby')
        day_name_el = soup.select_one(f'a#{label_id}') if label_id else None
        greek_day = day_name_el.get_text(strip=True) if day_name_el else ''
        # If this tab contains day headings, parse each day table within it (year-based page)
        day_headings = [
            h for h in tab.find_all(['h2', 'h3', 'h4', 'h5'])
            if h.get_text(strip=True) in DAY_MAP
        ]
        if day_headings:
            for h in day_headings:
                greek_day = h.get_text(strip=True)
                day = DAY_MAP.get(greek_day, greek_day)
                table = h.find_next('table', class_='courses_timetable')
                if not table:
                    continue
                rows = table.select('tr.sbody') or table.select('tr')[1:]
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
                        url=url,
                        year=tab_label or None
                    )
                    all_courses.append(course)
                    cid += 1
            continue

        # Fallback: single table per tab (week-based page)
        if not greek_day and tab_label:
            greek_day = tab_label
        day = DAY_MAP.get(greek_day, greek_day)
        rows = tab.select('table.courses_timetable tr.sbody')
        if not rows:
            rows = tab.select('table.courses_timetable tr')[1:]
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
                url=url,
                year=None
            )
            all_courses.append(course)
            cid += 1
    return all_courses


def load_from_file(path: Path) -> List[Course]:
    html_text = path.read_text(encoding='utf-8')
    return parse_programme_html(html_text)


def load_from_url(url: str, timeout: int = 15) -> List[Course]:
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=timeout) as resp:
        html_text = resp.read().decode('utf-8', 'ignore')
    return parse_programme_html(html_text)
