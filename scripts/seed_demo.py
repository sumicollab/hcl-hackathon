"""Repeatable DEVELOPMENT fixtures, not the required LLM-generated submission data."""
import csv
import json
from pathlib import Path
from app.config import Settings
from app.models import Source
from app.retrieval import KnowledgeBase
from app.storage import Database
from scripts.load_students import TABLES, load


def fixture_records():
    students, courses, attendance, results = [], [], [], []
    for i in range(30):
        programme = "B.Tech CSE" if i < 15 else "B.Tech ECE"
        students.append(dict(student_id=f"S{1001+i}", full_name=f"Synthetic Student {i+1}", programme=programme,
                             batch_year=2023 + i % 2, current_semester=5, cgpa=[7.0, 6.99, 8.0][i % 3], active_backlogs=i % 3))
    for i in range(6):
        programme = "B.Tech CSE" if i < 3 else "B.Tech ECE"
        code = ["CS201", "CS202", "CS203", "EC201", "EC202", "EC203"][i]
        courses.append(dict(course_code=code, course_name=["Data Structures", "Mathematics", "Databases", "Circuits", "Signals", "Electronics"][i],
                            programme=programme, semester=5, credits=4))
    for i, student in enumerate(students):
        for course in courses:
            if course["programme"] != student["programme"]:
                continue
            attendance.append(dict(student_id=student["student_id"], course_code=course["course_code"],
                                   classes_held=40, classes_attended=[30, 29, 32, 31][i % 4]))
            status = ["PASS", "FAIL", "ABSENT", "DETAINED"][i % 4]
            total = 60 if status == "PASS" else 39 if status == "FAIL" else 0
            results.append(dict(student_id=student["student_id"], course_code=course["course_code"],
                                exam_session="2026-MAY", exam_type="REGULAR", internal_marks=min(total, 20),
                                external_marks=max(total - 20, 0), total_marks=total, max_marks=100, result=status))
    return dict(students=students, courses=courses, attendance=attendance, results=results)


def seed(settings, directory=None):
    db = Database(settings.data_dir / "students.sqlite3")
    directory = directory or settings.data_dir / "demo_csv"
    directory.mkdir(parents=True, exist_ok=True)
    for table, records in fixture_records().items():
        with (directory / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TABLES[table])
            writer.writeheader()
            writer.writerows(records)
    counts = load(db, directory)
    kb = KnowledgeBase(db, settings)
    root = Path(__file__).resolve().parents[1] / "sample_documents"
    outcomes = []
    for entry in json.loads((root / "sources.json").read_text(encoding="utf-8")):
        filename = entry.pop("filename")
        outcomes.append(kb.ingest((root / filename).read_bytes(), filename, Source(**entry)))
    with (settings.data_dir / "source_register.csv").open("w", newline="", encoding="utf-8") as handle:
        register = db.sources()
        writer = csv.DictWriter(handle, fieldnames=list(register[0]))
        writer.writeheader()
        writer.writerows(register)
    print({"development_fixtures_only": True, "counts": counts, "documents": outcomes})


if __name__ == "__main__":
    seed(Settings.from_env())
