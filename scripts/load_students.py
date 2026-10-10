"""Load fixed-schema CSVs in one transaction. Safe to re-run identical rows."""
import argparse
import csv
from pathlib import Path
from app.config import Settings
from app.storage import Database

TABLES = {
    "students": ["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"],
    "courses": ["course_code", "course_name", "programme", "semester", "credits"],
    "attendance": ["student_id", "course_code", "classes_held", "classes_attended"],
    "results": ["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks", "total_marks", "max_marks", "result"],
}
KEYS = {"students": ["student_id"], "courses": ["course_code"], "attendance": ["student_id", "course_code"],
        "results": ["student_id", "course_code", "exam_session", "exam_type"]}


def load(db, directory):
    counts = {}
    with db.connect() as conn:
        for table, columns in TABLES.items():
            path = Path(directory) / f"{table}.csv"
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or not set(columns) <= set(reader.fieldnames):
                    raise ValueError(f"{table}: missing required columns")
                records = list(reader)
            for row in records:
                if table == "students":
                    import re
                    if not re.fullmatch(r"S\d{4}", row["student_id"]):
                        raise ValueError("Invalid student ID")
                if table == "attendance" and int(row["classes_attended"]) > int(row["classes_held"]):
                    raise ValueError("Attendance exceeds classes held")
                if table == "results":
                    if int(row["total_marks"]) != int(row["internal_marks"]) + int(row["external_marks"]):
                        raise ValueError("Marks total does not match components")
                keys = KEYS[table]
                updates = [c for c in columns if c not in keys]
                sql = (f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                       f"ON CONFLICT ({','.join(keys)}) DO UPDATE SET " + ','.join(f"{c}=excluded.{c}" for c in updates))
                conn.execute(sql, tuple(row[c] for c in columns))
            counts[table] = len(records)
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    args = parser.parse_args()
    print(load(Database(Settings.from_env().data_dir / "students.sqlite3"), args.dir))
