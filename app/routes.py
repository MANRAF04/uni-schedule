from __future__ import annotations
from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from datetime import time, date
import re
import urllib.request
import urllib.parse
import http.cookiejar
from bs4 import BeautifulSoup
from . import COURSES, COURSES_BY_ID
from .parser import load_from_file
from .ical import generate_ics
from .models import Course
from pathlib import Path
import threading
import json

bp = Blueprint('main', __name__)

# Lazy load lock
_loaded = False
_lock = threading.Lock()

PROGRAMME_SOURCE = Path(__file__).resolve().parent.parent / 'programme.htm'
SPRING_PROGRAMME_URL = 'https://www.e-ce.uth.gr/studies/undergraduate/spring-timetable/year/'
FALL_PROGRAMME_URL = 'https://www.e-ce.uth.gr/studies/undergraduate/fall-timetable/year/'
PERSIST_FILE = Path(__file__).resolve().parent.parent / 'remaining_courses.json'


def _semester_url(today: date) -> str:
    # Spring semester typically Feb–Jun; fall/winter otherwise
    if 2 <= today.month <= 6:
        return SPRING_PROGRAMME_URL
    return FALL_PROGRAMME_URL


def _course_key(title: str, day: str, start: str, end: str, kind: str, room: str) -> str:
    return f"{title}|{day}|{start}|{end}|{kind}|{room}".lower().strip()


def _course_key_from_course(c: Course) -> str:
    return _course_key(
        c.title,
        c.day,
        c.start.strftime('%H:%M'),
        c.end.strftime('%H:%M'),
        c.kind,
        c.room
    )


def _normalize_title(title: str) -> str:
    t = title.strip()
    t = re.sub(r'^[A-Za-zΑ-ΩΪΫ]{2,}\d+[A-Za-zΑ-ΩΪΫ]?\s+', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.lower()


def _fetch_requirement_map(target_titles: list[str]) -> dict[str, str]:
    """Return mapping of normalized course title -> requirement ('required'|'elective') when available."""
    if not target_titles:
        return {}
    page = 'https://www.e-ce.uth.gr/studies/undergraduate/courses/'
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        html = opener.open(urllib.request.Request(page, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15).read().decode('utf-8', 'ignore')
    except Exception:
        return {}
    nonce_match = re.search(r'"ajax_nonce":"([a-f0-9]+)"', html)
    nonce = nonce_match.group(1) if nonce_match else None
    if not nonce:
        return {}

    soup = BeautifulSoup(html, 'html.parser')
    title_to_id: dict[str, str] = {}
    for wrap in soup.select('div.toggle_ajax-wrap'):
        cid = wrap.get('id')
        title_el = wrap.select_one('h3.trigger_ajax a')
        if not cid or not title_el:
            continue
        raw_title = title_el.get_text(strip=True)
        norm_title = _normalize_title(raw_title)
        if norm_title:
            title_to_id.setdefault(norm_title, cid)

    needed = { _normalize_title(t) for t in target_titles if t }
    if not needed:
        return {}

    url = 'https://www.e-ce.uth.gr/wp-admin/admin-ajax.php'
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': page,
        'Origin': 'https://www.e-ce.uth.gr',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Accept': '*/*'
    }
    result: dict[str, str] = {}
    for norm_title in needed:
        cid = title_to_id.get(norm_title)
        if not cid:
            continue
        try:
            params = {'action': 'course_Details_Gr', 'courseId': cid, 'security': nonce}
            data = urllib.parse.urlencode(params).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers)
            resp = opener.open(req, timeout=15)
            detail_html = resp.read().decode('utf-8', 'ignore')
        except Exception:
            return {}
        if 'Υποχρεωτικό' in detail_html:
            result[norm_title] = 'required'
        elif 'Επιλογής' in detail_html or 'Μάθημα Επιλογής' in detail_html:
            result[norm_title] = 'elective'
    return result


def _save_state():
    data = [
        {
            'id': c.id,
            'title': c.title,
            'day': c.day,
            'start': c.start.strftime('%H:%M'),
            'end': c.end.strftime('%H:%M'),
            'kind': c.kind,
            'room': c.room,
            'instructors': c.instructors,
            'url': c.url,
            'year': c.year,
            'active': c.active,
            'requirement': c.requirement
        } for c in COURSES
    ]
    PERSIST_FILE.write_text(json.dumps({'courses': data}, ensure_ascii=False, indent=2), encoding='utf-8')


def active_courses() -> list[Course]:
    return [c for c in COURSES if c.active]


def visible_courses() -> list[Course]:
    return list(COURSES)


def ensure_loaded():
    global _loaded
    if not _loaded:
        with _lock:
            if not _loaded:
                courses = []
                active_by_key: dict[str, bool] = {}
                requirement_by_key: dict[str, str] = {}
                has_legacy_remaining = False
                if PERSIST_FILE.exists():
                    try:
                        data = json.loads(PERSIST_FILE.read_text(encoding='utf-8'))
                        if 'remaining' in data and 'courses' not in data:
                            has_legacy_remaining = True
                            for item in data.get('remaining', []):
                                key = _course_key(
                                    item.get('title', ''),
                                    item.get('day', ''),
                                    item.get('start', ''),
                                    item.get('end', ''),
                                    item.get('kind', ''),
                                    item.get('room', '')
                                )
                                active_by_key[key] = True
                        for item in data.get('courses', []):
                            key = _course_key(
                                item.get('title', ''),
                                item.get('day', ''),
                                item.get('start', ''),
                                item.get('end', ''),
                                item.get('kind', ''),
                                item.get('room', '')
                            )
                            active_by_key[key] = bool(item.get('active', True))
                            if item.get('requirement') in ('required', 'elective'):
                                requirement_by_key[key] = item.get('requirement')
                    except Exception:
                        pass
                # Always fetch from the website each app start
                try:
                    from datetime import date
                    from .parser import load_from_url
                    courses = load_from_url(_semester_url(date.today()))
                except Exception:
                    if PROGRAMME_SOURCE.exists():
                        from .parser import load_from_file
                        courses = load_from_file(PROGRAMME_SOURCE)

                # Apply saved active state by stable key
                for c in courses:
                    key = _course_key_from_course(c)
                    if key in active_by_key:
                        c.active = active_by_key[key]
                    elif has_legacy_remaining:
                        c.active = False
                    if key in requirement_by_key:
                        c.requirement = requirement_by_key[key]

                # Try to fetch missing requirement info (best effort)
                missing_titles = [c.title for c in courses if not c.requirement]
                if missing_titles:
                    req_map = _fetch_requirement_map(missing_titles)
                    if req_map:
                        for c in courses:
                            if not c.requirement:
                                req = req_map.get(_normalize_title(c.title))
                                if req:
                                    c.requirement = req
                        _save_state()
                COURSES.clear()
                COURSES_BY_ID.clear()
                for c in courses:
                    COURSES.append(c)
                    COURSES_BY_ID[c.id] = c
                _loaded = True


def group_by_day():
    ensure_loaded()
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    grouped = {d: [] for d in days}
    for c in visible_courses():
        grouped.setdefault(c.day, []).append(c)
    # Sort by start time
    for d in grouped:
        grouped[d].sort(key=lambda c: (c.start.hour, c.start.minute))
    return grouped


def distinct_course_titles():
    ensure_loaded()
    return sorted({c.title for c in active_courses()})


@bp.route('/')
def index():
    grouped = group_by_day()
    distinct = distinct_course_titles()
    years = sorted({c.year for c in COURSES if c.year})
    requirements = sorted({c.requirement for c in COURSES if c.requirement})
    disabled_years = []
    for y in years:
        year_courses = [c for c in COURSES if c.year == y]
        if year_courses and all(not c.active for c in year_courses):
            disabled_years.append(y)
    disabled_requirements = []
    for r in requirements:
        r_courses = [c for c in COURSES if c.requirement == r]
        if r_courses and all(not c.active for c in r_courses):
            disabled_requirements.append(r)
    return render_template(
        'index.html',
        grouped=grouped,
        distinct_count=len(distinct),
        years=years,
        disabled_years=sorted(disabled_years),
        requirements=requirements,
        disabled_requirements=sorted(disabled_requirements)
    disabled_years=sorted(disabled_years),
    requirements=requirements,
    disabled_requirements=sorted(disabled_requirements)
    )


@bp.route('/remove/<int:course_id>', methods=['POST'])
def remove_course(course_id: int):
    ensure_loaded()
    toggled_ids = []
    new_state = None
    if course_id in COURSES_BY_ID:
        target = COURSES_BY_ID[course_id]
        target_title = target.title
        new_state = not target.active
        to_toggle = [c for c in COURSES if c.title == target_title]
        for c in to_toggle:
            c.active = new_state
            toggled_ids.append(c.id)
        _save_state()
    # If AJAX request expects JSON
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        active = active_courses()
        return jsonify({'status': 'ok', 'toggled_ids': toggled_ids, 'active': new_state, 'distinct_remaining': len({c.title for c in active})})
    return redirect(url_for('main.index'))


@bp.route('/year/disable/<path:year_label>', methods=['POST'])
def disable_year(year_label: str):
    ensure_loaded()
    if year_label:
        for c in COURSES:
            if c.year == year_label:
                c.active = False
        _save_state()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        active = active_courses()
        return jsonify({'status': 'disabled', 'year': year_label, 'distinct_remaining': len({c.title for c in active})})
    return redirect(url_for('main.index'))


@bp.route('/year/enable/<path:year_label>', methods=['POST'])
def enable_year(year_label: str):
    ensure_loaded()
    if year_label:
        for c in COURSES:
            if c.year == year_label:
                c.active = True
        _save_state()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        active = active_courses()
        return jsonify({'status': 'enabled', 'year': year_label, 'distinct_remaining': len({c.title for c in active})})
    return redirect(url_for('main.index'))


@bp.route('/type/disable/<path:req_label>', methods=['POST'])
def disable_requirement(req_label: str):
    ensure_loaded()
    if req_label in ('required', 'elective'):
        for c in COURSES:
            if c.requirement == req_label:
                c.active = False
        _save_state()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        active = active_courses()
        return jsonify({'status': 'disabled', 'type': req_label, 'distinct_remaining': len({c.title for c in active})})
    return redirect(url_for('main.index'))


@bp.route('/type/enable/<path:req_label>', methods=['POST'])
def enable_requirement(req_label: str):
    ensure_loaded()
    if req_label in ('required', 'elective'):
        for c in COURSES:
            if c.requirement == req_label:
                c.active = True
        _save_state()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        active = active_courses()
        return jsonify({'status': 'enabled', 'type': req_label, 'distinct_remaining': len({c.title for c in active})})
    return redirect(url_for('main.index'))


@bp.route('/api/courses')
def api_courses():
    ensure_loaded()
    active = active_courses()
    return jsonify({
        'distinct_count': len({c.title for c in active}),
        'courses': [
            {
                'id': c.id,
                'title': c.title,
                'day': c.day,
                'start': c.start.strftime('%H:%M'),
                'end': c.end.strftime('%H:%M'),
                'kind': c.kind,
                'room': c.room,
                'instructors': c.instructors,
                'url': c.url,
                'year': c.year,
                'active': c.active,
                'requirement': c.requirement
            } for c in active
        ]
    })


@bp.route('/api/export')
def export_remaining():
    ensure_loaded()
    active = active_courses()
    return jsonify({
        'remaining': [
            {
                'id': c.id,
                'title': c.title,
                'day': c.day,
                'start': c.start.strftime('%H:%M'),
                'end': c.end.strftime('%H:%M'),
                'kind': c.kind,
                'room': c.room,
                'instructors': c.instructors,
                'url': c.url,
                'year': c.year,
                'active': c.active,
                'requirement': c.requirement
            } for c in active
        ],
        'distinct_count': len({c.title for c in active})
    })


@bp.route('/export/ics')
def export_ics():
    """Download an iCalendar file for remaining courses.
    Query params:
      start=YYYY-MM-DD (defaults to today)
      weeks=number of weekly repetitions (default 12)
    """
    ensure_loaded()
    from datetime import datetime, date
    start_param = request.args.get('start')
    weeks_param = request.args.get('weeks')
    try:
        start_date = datetime.strptime(start_param, '%Y-%m-%d').date() if start_param else date.today()
    except ValueError:
        start_date = date.today()
    try:
        weeks = int(weeks_param) if weeks_param else 12
    except ValueError:
        weeks = 12
    ics_text = generate_ics(active_courses(), start_date=start_date, weeks=weeks)
    from flask import Response
    filename = f'schedule_{start_date.isoformat()}_{weeks}w.ics'
    return Response(
        ics_text,
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@bp.route('/reset', methods=['POST'])
def reset_schedule():
    """Delete persistence file and reload all courses from original HTML."""
    global _loaded
    if PERSIST_FILE.exists():
        try:
            PERSIST_FILE.unlink()
        except Exception:
            pass
    # Force reload on next access
    _loaded = False
    # Eager reload now so UI shows immediately
    ensure_loaded()
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        active = active_courses()
        return jsonify({'status': 'reset', 'remaining': len(active), 'distinct_remaining': len({c.title for c in active})})
    return redirect(url_for('main.index'))
