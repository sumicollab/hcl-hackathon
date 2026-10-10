"""The HTTP boundary. Start with: uvicorn app.main:app --port 8000"""
import hmac
import json
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import ValidationError

from .config import Settings
from .models import Answer, AskRequest, Source
from .retrieval import KnowledgeBase
from .service import Assistant
from .storage import Database


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(api):
        db = Database(settings.data_dir / "students.sqlite3")
        kb = KnowledgeBase(db, settings)
        api.state.db, api.state.kb = db, kb
        api.state.assistant = Assistant(db, kb, settings)
        yield

    api = FastAPI(title="University Student Services MVP", lifespan=lifespan)

    def require_admin(token):
        if not settings.admin_token or not token or not hmac.compare_digest(token, settings.admin_token):
            raise HTTPException(403, "A configured X-Admin-Token is required.")

    @api.post("/ask", response_model=Answer)
    def ask(body: AskRequest, x_student_id: str | None = Header(default=None)):
        import re
        if x_student_id and not re.fullmatch(r"S\d{4}", x_student_id):
            raise HTTPException(422, "Student ID must be S followed by four digits.")
        try:
            return api.state.assistant.ask(body, x_student_id)
        except (httpx.HTTPError, ValueError) as error:
            # Operational failure is not misleadingly reported as missing policy evidence.
            raise HTTPException(503, "AI service unavailable or invalid output; check /health.") from error

    @api.post("/ingest")
    def ingest(file: UploadFile = File(), metadata: str = Form(), x_admin_token: str | None = Header(default=None)):
        require_admin(x_admin_token)
        try:
            source = Source.model_validate_json(metadata)
            content = file.file.read(10 * 1024 * 1024 + 1)
            if len(content) > 10 * 1024 * 1024:
                raise ValueError("Maximum document size is 10 MB.")
            return api.state.kb.ingest(content, file.filename or "upload.pdf", source)
        except (ValueError, ValidationError) as error:
            raise HTTPException(422, str(error)) from error

    @api.get("/sources")
    def sources():
        return api.state.db.sources()

    @api.get("/audit/{trace_id}")
    def audit(trace_id: str, x_student_id: str | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
        rows = api.state.db.rows("SELECT student_id, record FROM audits WHERE trace_id=?", (trace_id,))
        admin = settings.admin_token and x_admin_token and hmac.compare_digest(x_admin_token, settings.admin_token)
        if not rows or (not admin and rows[0]["student_id"] != x_student_id):
            raise HTTPException(404, "Audit not found.")
        return json.loads(rows[0]["record"])

    @api.get("/health")
    def health():
        ready = settings.mock_llm
        llm_status = "mock" if ready else "unavailable"
        if not ready:
            try:
                response = httpx.get(settings.ollama_url + "/api/tags", timeout=3)
                response.raise_for_status()
                ready = any(m["name"] == settings.ollama_model for m in response.json().get("models", []))
                llm_status = "ready" if ready else "model_not_pulled"
            except (httpx.HTTPError, ValueError):
                pass
        api.state.db.rows("SELECT 1")
        return {"status": "ready" if ready else "degraded", "api": "ready", "sqlite": "ready",
                "vector_store": "ready", "chunks": api.state.kb.collection.count(), "llm": llm_status,
                "model": settings.ollama_model, "embedding_backend": settings.embedding_backend,
                "mock_llm": settings.mock_llm}

    return api


app = create_app()
