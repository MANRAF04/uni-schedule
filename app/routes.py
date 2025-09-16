from __future__ import annotations
from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from datetime import time
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
PERSIST_FILE = Path(__file__).resolve().parent.parent / 'remaining_courses.json'


def ensure_loaded():
    global _loaded
    if not _loaded:
        with _lock:
            if not _loaded:
                courses = []
                if PERSIST_FILE.exists():
                    try:
                        data = json.loads(PERSIST_FILE.read_text(encoding='utf-8'))
                        from datetime import datetime
                        from .models import Course
                        for item in data.get('remaining', []):
                            start = datetime.strptime(item['start'], '%H:%M').time()
                            end = datetime.strptime(item['end'], '%H:%M').time()
                            c = Course(
                                id=item['id'],
                                title=item['title'],
                                day=item['day'],
                                start=start,
                                end=end,
                                kind=item.get('kind',''),
                                room=item.get('room',''),
                                instructors=item.get('instructors',[]),
                                url=item.get('url')
                            )
                            courses.append(c)
                    except Exception:
                        pass
                if not courses and PROGRAMME_SOURCE.exists():
                    from .parser import load_from_file
                    courses = load_from_file(PROGRAMME_SOURCE)
                # Backfill missing URLs if any course lacks one and original source exists
                if any(c.url is None for c in courses) and PROGRAMME_SOURCE.exists():
                    try:
                        from .parser import load_from_file as _parse_all
                        full_courses = _parse_all(PROGRAMME_SOURCE)
                        # build lookup by (title, day, start, end)
                        index = { (fc.title, fc.day, fc.start.strftime('%H:%M'), fc.end.strftime('%H:%M')): fc for fc in full_courses }
                        for c in courses:
                            if c.url is None:
                                key = (c.title, c.day, c.start.strftime('%H:%M'), c.end.strftime('%H:%M'))
                                match = index.get(key)
                                if match and match.url:
                                    c.url = match.url
                    except Exception:
                        pass
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
    for c in COURSES:
        grouped.setdefault(c.day, []).append(c)
    # Sort by start time
    for d in grouped:
        grouped[d].sort(key=lambda c: (c.start.hour, c.start.minute))
    return grouped


def distinct_course_titles():
    ensure_loaded()
    return sorted({c.title for c in COURSES})


@bp.route('/')
def index():
    grouped = group_by_day()
    distinct = distinct_course_titles()
    return render_template('index.html', grouped=grouped, distinct_count=len(distinct))


@bp.route('/remove/<int:course_id>', methods=['POST'])
def remove_course(course_id: int):
    ensure_loaded()
    removed_ids = []
    if course_id in COURSES_BY_ID:
        # Identify title of selected course
        target_title = COURSES_BY_ID[course_id].title
        # Collect all courses with same title
        to_remove = [c for c in COURSES if c.title == target_title]
        removed_ids = [c.id for c in to_remove]
        # Rebuild course list excluding them
        remaining = [c for c in COURSES if c.title != target_title]
        COURSES.clear()
        COURSES.extend(remaining)
        # Rebuild id index
        COURSES_BY_ID.clear()
        for c in COURSES:
            COURSES_BY_ID[c.id] = c
        # Persist remaining
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
                'url': c.url
            } for c in COURSES
        ]
        PERSIST_FILE.write_text(json.dumps({'remaining': data}, ensure_ascii=False, indent=2), encoding='utf-8')
    # If AJAX request expects JSON
    if request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'status': 'ok', 'removed_ids': removed_ids, 'remaining': len(COURSES), 'distinct_remaining': len({c.title for c in COURSES})})
    return redirect(url_for('main.index'))


@bp.route('/api/courses')
def api_courses():
    ensure_loaded()
    return jsonify({
        'distinct_count': len({c.title for c in COURSES}),
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
                'url': c.url
            } for c in COURSES
        ]
    })


@bp.route('/api/export')
def export_remaining():
    ensure_loaded()
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
                'url': c.url
            } for c in COURSES
        ],
        'distinct_count': len({c.title for c in COURSES})
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
    ics_text = generate_ics(COURSES, start_date=start_date, weeks=weeks)
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
        return jsonify({'status': 'reset', 'remaining': len(COURSES), 'distinct_remaining': len({c.title for c in COURSES})})
    return redirect(url_for('main.index'))
