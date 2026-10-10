import io
import sqlite3
from unittest.mock import Mock
import pytest
from scripts import start


def test_backend_failure_stops_startup():
    process = Mock()
    process.poll.return_value = 1
    with pytest.raises(RuntimeError, match="exited before"):
        start.wait_for_backend(process, "http://127.0.0.1:8000")


def test_backend_health_is_required(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(start, "urlopen", lambda *a, **k: io.BytesIO(b'{"mock_llm":true,"api":"ready"}'))
    assert start.wait_for_backend(process, "http://127.0.0.1:8000")["api"] == "ready"


def test_demo_setup_preserves_populated_students(tmp_path):
    assert start.needs_demo_data(tmp_path)
    with sqlite3.connect(tmp_path / "students.sqlite3") as connection:
        connection.execute("CREATE TABLE students(student_id TEXT)")
        connection.execute("INSERT INTO students VALUES ('S1001')")
    assert not start.needs_demo_data(tmp_path)
