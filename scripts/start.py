"""Start both services with the same Python environment and verify API readiness."""
import argparse
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def available_port(preferred):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", preferred))
        except OSError:
            probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_backend(process, url, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Backend exited before it was ready.")
        try:
            with urlopen(url + "/health", timeout=2) as response:
                health = json.load(response)
            if "mock_llm" in health:
                return health
        except (URLError, TimeoutError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("Backend startup timed out after 180 seconds.")


def needs_demo_data(directory):
    database = directory / "students.sqlite3"
    if not database.exists():
        return True
    with sqlite3.connect(database) as connection:
        try:
            return connection.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0
        except sqlite3.OperationalError:
            return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Explicit mock LLM and synthetic starter data.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(root / "runtime" / "models"))
    if args.demo:
        env["MOCK_LLM"] = "true"
        print("Development demo: mock LLM, actual MiniLM embeddings, synthetic policies.", flush=True)
    directory = Path(env.get("DATA_DIR", "runtime"))
    directory.mkdir(parents=True, exist_ok=True)
    if args.demo and needs_demo_data(directory):
        print("Preparing sample data. First run may download the embedding model; please wait.", flush=True)
        subprocess.run([sys.executable, "-m", "scripts.seed_demo"], env=env, check=True)
    api_port, ui_port = available_port(8000), available_port(8501)
    env["API_URL"] = f"http://127.0.0.1:{api_port}"
    log_path = directory / "backend.log"
    backend = frontend = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            print(f"Starting backend. Startup errors are saved in {log_path.resolve()}", flush=True)
            backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
                                        "--host", "127.0.0.1", "--port", str(api_port)],
                                       env=env, stdout=log, stderr=subprocess.STDOUT)
            health = wait_for_backend(backend, env["API_URL"])
            print(f"Backend ready at {env['API_URL']} (LLM: {health.get('llm')}).", flush=True)
            if not health["mock_llm"] and health.get("llm") != "ready":
                print("Check /health for Ollama status before asking AI questions.", flush=True)
            print(f"Open http://127.0.0.1:{ui_port}. Keep this terminal open; Ctrl+C stops both services.", flush=True)
            frontend = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "ui.py",
                                         "--server.address", "127.0.0.1", "--server.port", str(ui_port)], env=env)
            while frontend.poll() is None:
                if backend.poll() is not None:
                    raise RuntimeError("Backend stopped while the frontend was running.")
                time.sleep(1)
            if frontend.returncode:
                raise RuntimeError("Frontend failed; see the terminal error above.")
    except KeyboardInterrupt:
        print("Stopping both services.")
    except RuntimeError as error:
        print(f"\n{error}\nBackend log:\n{log_path.read_text(encoding='utf-8', errors='replace')}", file=sys.stderr)
        return 1
    finally:
        for process in (frontend, backend):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
