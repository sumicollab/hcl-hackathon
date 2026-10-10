"""SQLite stores exact records. SQL values are always bound parameters."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS students (
 student_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, programme TEXT NOT NULL,
 batch_year INTEGER NOT NULL, current_semester INTEGER CHECK(current_semester BETWEEN 1 AND 10),
 cgpa REAL CHECK(cgpa BETWEEN 0 AND 10), active_backlogs INTEGER CHECK(active_backlogs >= 0));
CREATE TABLE IF NOT EXISTS courses (
 course_code TEXT PRIMARY KEY, course_name TEXT, programme TEXT, semester INTEGER, credits INTEGER);
CREATE TABLE IF NOT EXISTS attendance (
 student_id TEXT REFERENCES students(student_id), course_code TEXT REFERENCES courses(course_code),
 classes_held INTEGER CHECK(classes_held > 0), classes_attended INTEGER,
 CHECK(classes_attended BETWEEN 0 AND classes_held), PRIMARY KEY(student_id, course_code));
CREATE TABLE IF NOT EXISTS results (
 student_id TEXT REFERENCES students(student_id), course_code TEXT REFERENCES courses(course_code),
 exam_session TEXT, exam_type TEXT CHECK(exam_type IN ('REGULAR','SUPPLEMENTARY')),
 internal_marks INTEGER, external_marks INTEGER, total_marks INTEGER, max_marks INTEGER,
 result TEXT CHECK(result IN ('PASS','FAIL','ABSENT','DETAINED')),
 CHECK(total_marks = internal_marks + external_marks),
 CHECK(internal_marks >= 0 AND external_marks >= 0 AND total_marks BETWEEN 0 AND max_marks),
 PRIMARY KEY(student_id,course_code,exam_session,exam_type));
CREATE TABLE IF NOT EXISTS sources (doc_id TEXT PRIMARY KEY, metadata TEXT NOT NULL, digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chunks (
 chunk_id TEXT PRIMARY KEY, doc_id TEXT REFERENCES sources(doc_id), section TEXT, page INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS rule_registry (
 rule_id TEXT PRIMARY KEY, description TEXT, parameter TEXT, operator TEXT, value TEXT,
 scope_programmes TEXT, scope_batches TEXT, effective_from TEXT, effective_to TEXT,
 source_doc_id TEXT REFERENCES sources(doc_id), source_section TEXT);
CREATE TABLE IF NOT EXISTS audits (trace_id TEXT PRIMARY KEY, student_id TEXT, record TEXT NOT NULL);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, query, values=()):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, values).fetchall()]

    def sources(self):
        return [json.loads(row["metadata"]) for row in self.rows("SELECT metadata FROM sources")]

    def student(self, student_id):
        rows = self.rows("SELECT * FROM students WHERE student_id = ?", (student_id,))
        return rows[0] if rows else None

    def audit(self, trace_id, student_id, record):
        with self.connect() as conn:
            conn.execute("INSERT INTO audits VALUES (?, ?, ?)", (trace_id, student_id, json.dumps(record)))
