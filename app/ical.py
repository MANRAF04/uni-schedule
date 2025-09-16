from __future__ import annotations
from datetime import datetime, date, time, timedelta
from typing import Iterable, Tuple, List
from .models import Course
import uuid

# Map English day to weekday index (Monday=0)
WEEKDAY_INDEX = {
    'Monday': 0,
    'Tuesday': 1,
    'Wednesday': 2,
    'Thursday': 3,
    'Friday': 4,
    'Saturday': 5,
    'Sunday': 6,
}

def _next_date(start: date, target_weekday: int) -> date:
    days_ahead = (target_weekday - start.weekday()) % 7
    return start + timedelta(days=days_ahead)

def generate_ics(courses: Iterable[Course], start_date: date, weeks: int = 12, tz: str = 'Europe/Athens',
                 holidays: List[Tuple[date, date]] | None = None) -> str:
    """Generate an .ics calendar string for the given courses.

    Args:
        courses: Iterable of Course objects.
        start_date: First Monday (or earlier reference date) of the academic period.
        weeks: Number of weeks to repeat.
        tz: IANA timezone name (not fully embedded as VTIMEZONE here; events use floating/local time).
    """
    # Normalize start_date to Monday for consistency (optional)
    base_monday = start_date - timedelta(days=start_date.weekday())
    now_stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

    # Holiday ranges (inclusive) default: Christmas/New Year break specified by user
    # Provided: from Tuesday 23/12/2025 till Tuesday 06/01/2026 (inclusive)
    if holidays is None:
        holidays = [ (date(2025,12,23), date(2026,1,6)) ]

    def is_holiday(d: date) -> bool:
        for start, end in holidays:
            if start <= d <= end:
                return True
        return False

    lines = [
        'BEGIN:VCALENDAR',
        'PRODID:-//Uni Programme Export//EN',
        'VERSION:2.0',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-TIMEZONE:{tz}',
    ]

    # Sort courses for deterministic output
    courses_list = sorted(courses, key=lambda c: (c.day, c.start, c.title))

    byday_map = {0:'MO',1:'TU',2:'WE',3:'TH',4:'FR',5:'SA',6:'SU'}

    for c in courses_list:
        wd = WEEKDAY_INDEX.get(c.day)
        if wd is None:
            continue
        event_date = _next_date(base_monday, wd)
        dt_start = datetime.combine(event_date, c.start)
        dt_end = datetime.combine(event_date, c.end)
        uid = f'{c.id}-{uuid.uuid4().hex[:8]}@uni-programme'
        dt_fmt = '%Y%m%dT%H%M%S'
        dtstart_str = dt_start.strftime(dt_fmt)
        dtend_str = dt_end.strftime(dt_fmt)
        byday = byday_map[wd]
        summary = c.title.replace('\n', ' ')
        location = (c.room or '').replace('\n',' ')
        instructors = ', '.join(c.instructors)
        desc_parts = [f'Type: {c.kind}', f'Room: {c.room}']
        if instructors:
            desc_parts.append(f'Instructors: {instructors}')
        if c.url:
            desc_parts.append(f'Link: {c.url}')
        description = '\n'.join(desc_parts)
        # Escape commas, semicolons, backslashes per RFC 5545
        def esc(s: str) -> str:
            return s.replace('\\', '\\\\').replace(';', '\;').replace(',', '\,')
        # We need to adjust for holidays so that COUNT reflects teaching weeks only.
        # Strategy: expand week dates skipping holidays until we have `weeks` teaching occurrences.
        # We'll produce explicit EXDATEs for holiday occurrences OR simply extend COUNT and list EXDATE.
        # To keep file simpler and smaller, we'll add EXDATE entries and keep COUNT extended.

        # Collect holiday dates that would have been within the first `weeks` teaching weeks window
        teaching_dates = []
        exdates = []
        current_date = event_date
        while len(teaching_dates) < weeks:
            if is_holiday(current_date):
                exdates.append(current_date)
            else:
                teaching_dates.append(current_date)
            current_date += timedelta(days=7)
        # Total weeks spanned is weeks + number of holiday hits among them
        total_occurrences = weeks + len(exdates)

        lines.extend([
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTAMP:{now_stamp}',
            f'DTSTART:{dtstart_str}',
            f'DTEND:{dtend_str}',
            f'SUMMARY:{esc(summary)}',
            f'LOCATION:{esc(location)}',
            f'DESCRIPTION:{esc(description)}',
            f'RRULE:FREQ=WEEKLY;COUNT={total_occurrences};BYDAY={byday}',
        ])
        # Add EXDATE lines for each holiday occurrence that matched weekday
        for hd in exdates:
            lines.append(f'EXDATE:{hd.strftime("%Y%m%dT%H%M%S").replace("T000000","T" + c.start.strftime("%H%M%S"))}')
        lines.append('END:VEVENT')

    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'
