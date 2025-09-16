from pathlib import Path
from app.parser import load_from_file

def test_load_parses_courses():
    html_path = Path(__file__).resolve().parent.parent / 'programme.htm'
    if not html_path.exists():
        return  # skip if source not present in test env
    courses = load_from_file(html_path)
    assert len(courses) > 0
    # Basic property check
    first = courses[0]
    assert first.start < first.end
