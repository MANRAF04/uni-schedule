# Weekly Schedule Web App

A small Flask web application that parses the provided `programme.htm` (original timetable in Greek) and shows a weekly schedule (Monday–Friday). You can remove courses you don't want and export the remaining schedule as JSON.

## Features
- Parses original HTML (Greek day names → English) using BeautifulSoup (built-in html.parser)
- Displays grouped courses by day with time ordering
- Remove courses (in-memory only) via a button
- JSON endpoints:
  - `/api/courses` list all current (remaining) courses
  - `/api/export` export remaining courses
  - `/export/ics` download an iCalendar file (import into Google Calendar)

## Requirements
Python 3.11+ recommended.

## Setup
```bash
python -m venv .venv
# Windows PowerShell activate:
. .venv/Scripts/Activate.ps1
# Windows Command Prompt activate:
.venv\Scripts\activate.bat
# Linux activate:
./venv/bin/activate
pip install -r requirements.txt
python run.py
```
Visit: http://127.0.0.1:5000/

## Notes
- Removals are not persisted; restarting the server reloads original timetable.
- To persist, you could extend by writing remaining courses to a JSON file and reloading from it first if present.
- iCalendar export: visit `/export/ics?start=2025-09-15&weeks=15` (adjust start Monday date & number of weeks).
- iCalendar export: visit `/export/ics?start=2025-09-22&weeks=15` (navigation bar has a direct "Export ICS (15w)" link for this default semester span).
- Reset full schedule: use the "Reset" button (or POST `/reset`) to delete `remaining_courses.json` and reload original data.
- Bulk removal: removing one occurrence of a course now removes ALL its sessions (same title across different days) in one action.
- Distinct counter: the large number near the title shows how many unique course titles remain (multiple sessions of the same course count once).
- ICS holiday exclusion: The generated .ics automatically skips the holiday break from 2025-12-23 through 2026-01-06 (inclusive) using EXDATE entries while still delivering the requested number of teaching weeks.
- Greek localization: UI (titles, buttons, weekday labels, counter) now displayed in Greek.

## Google Calendar Import
1. Go to Google Calendar (web).
2. Left sidebar: Settings & Import → Import.
3. Choose the downloaded `.ics` file from `/export/ics` route.
4. Select (or create) a destination calendar and import.
5. Recurring weekly events are created with the specified count.

If you need semester-specific dates, pass a `start` query param (first week Monday) and `weeks` length.

## Tests
Basic parser test:
```bash
pytest -q
```

## Next Ideas
- Add drag & drop, filtering, or color coding by course type.
- Add persistence (JSON or SQLite) and user sessions.
- Add localization toggle (Greek/English days).
