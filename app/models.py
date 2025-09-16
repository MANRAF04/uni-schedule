from dataclasses import dataclass, field
from datetime import time
from typing import List, Optional


@dataclass
class Course:
    id: int
    title: str
    day: str  # English day name: Monday, Tuesday, ...
    start: time
    end: time
    kind: str  # Lecture, Lab, etc.
    room: str
    instructors: List[str] = field(default_factory=list)
    original_html: Optional[str] = None
    url: Optional[str] = None

    @property
    def duration_hours(self) -> float:
        return (self.end.hour + self.end.minute/60) - (self.start.hour + self.start.minute/60)
