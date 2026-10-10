"""Generate actual LLM-assisted synthetic records and preserve provenance.

Run against Ollama, then validate. Seed_demo is a separate deterministic fixture.
"""
import argparse
import csv
import json
from pathlib import Path
from pydantic import BaseModel
from app.config import Settings
from app.llm import LocalLLM
from scripts.load_students import TABLES
from scripts.validate_data import validate


class Student(BaseModel):
    student_id: str
    full_name: str
    programme: str
    batch_year: int
    current_semester: int
    cgpa: float
    active_backlogs: int


class Course(BaseModel):
    course_code: str
    course_name: str
    programme: str
    semester: int
    credits: int


class Attendance(BaseModel):
    student_id: str
    course_code: str
    classes_held: int
    classes_attended: int


class Result(BaseModel):
    student_id: str
    course_code: str
    exam_session: str
    exam_type: str
    internal_marks: int
    external_marks: int
    total_marks: int
    max_marks: int
    result: str


class Dataset(BaseModel):
    students: list[Student]
    courses: list[Course]
    attendance: list[Attendance]
    results: list[Result]


def generate(directory, attendance_threshold, pass_mark):
    settings = Settings.from_env()
    if settings.mock_llm:
        raise ValueError("Generation requires real Ollama. MOCK_LLM must be false.")
    directory.mkdir(parents=True, exist_ok=True)
    prompt = (
        "Generate synthetic university records, no real people. Return the supplied JSON schema. "
        "At least 30 students S1001 onward, two programmes B.Tech CSE and B.Tech ECE, batches 2023 and 2024, "
        "six courses across the programmes. Each attendance/result must reference existing matching students/courses. "
        "Current semester 1..10, CGPA 0..10, active_backlogs>=0. Held>0; attended between 0 and held. "
        f"Attendance threshold is {attendance_threshold}%; include exactly at threshold and one class below. "
        f"Pass mark is {pass_mark}/100; include FAIL at one mark below and PASS at the boundary. "
        "Marks total=internal+external, within 0..100; include ABSENT, DETAINED, multiple backlogs and CGPA=7.0. "
        "exam_type REGULAR or SUPPLEMENTARY. Do not use S9000..S9999 or JDG-prefixed courses."
    )
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    llm = LocalLLM(settings)
    records = llm.structured("Generate structured synthetic data, obey all constraints.", {"prompt": prompt}, Dataset)
    for table, rows in records.model_dump().items():
        with (directory / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TABLES[table])
            writer.writeheader()
            writer.writerows(rows)
    report = validate(directory, pass_mark)
    provenance = {"model": settings.ollama_model, "temperature": 0, "calls": llm.calls,
                  "tokens": llm.tokens, "validation": report}
    (directory / "generation_report.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    if not report["valid"]:
        raise ValueError("Generated records failed validation. Inspect generation_report.json; correct or regenerate.")
    print(provenance)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="runtime/generated")
    parser.add_argument("--attendance-threshold", type=float, required=True)
    parser.add_argument("--pass-mark", type=float, required=True)
    args = parser.parse_args()
    generate(Path(args.dir), args.attendance_threshold, args.pass_mark)
