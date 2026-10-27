"""SQLite storage for students and their daily attendance."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    mat_no        TEXT NOT NULL UNIQUE,
    level         TEXT NOT NULL,
    face_template BLOB NOT NULL,          -- 128 float32 values; the photo itself is not kept
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance (
    id         TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    date       TEXT NOT NULL,             -- local date, so a student is marked at most once a day
    timestamp  TEXT NOT NULL,
    similarity REAL NOT NULL,
    status     TEXT NOT NULL DEFAULT 'present',
    UNIQUE (student_id, date)
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()
