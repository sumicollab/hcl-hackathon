"""Validate CSV integrity without modifying the application's database."""
import argparse
import tempfile
from pathlib import Path
from app.storage import Database
from scripts.load_students import load


def validate(directory, pass_mark=None):
    with tempfile.TemporaryDirectory() as folder:
        db = Database(Path(folder) / "validation.sqlite3")
        counts = load(db, directory)
        errors = []
        if counts["students"] < 30 or counts["courses"] < 6:
            errors.append("Need at least 30 students and 6 courses")
        if len(db.rows("SELECT DISTINCT programme FROM students")) < 2:
            errors.append("Need at least two programmes")
        if len(db.rows("SELECT DISTINCT batch_year FROM students")) < 2:
            errors.append("Need at least two batches")
        if db.rows("SELECT student_id FROM students WHERE student_id BETWEEN 'S9000' AND 'S9999'"):
            errors.append("Generated data uses reserved judge student IDs")
        if db.rows("SELECT course_code FROM courses WHERE course_code LIKE 'JDG%'"):
            errors.append("Generated data uses reserved judge course codes")
        if db.rows("SELECT a.student_id FROM attendance a JOIN students s USING(student_id) JOIN courses c USING(course_code) WHERE s.programme != c.programme"):
            errors.append("Attendance course belongs to a different programme")
        if pass_mark is not None:
            bad = db.rows("SELECT student_id FROM results WHERE (result='PASS' AND total_marks<?) OR (result='FAIL' AND total_marks>=?)", (pass_mark, pass_mark))
            if bad:
                errors.append("PASS/FAIL result inconsistent with the supplied policy pass mark")
        return {"counts": counts, "violations": errors, "valid": not errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--pass-mark", type=float, help="Use the pass mark from your official policy")
    args = parser.parse_args()
    report = validate(args.dir, args.pass_mark)
    print(report)
    raise SystemExit(0 if report["valid"] else 1)
