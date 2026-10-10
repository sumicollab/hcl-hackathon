"""Pydantic models are the forms that every component must fill correctly."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from zoneinfo import ZoneInfo


def today_ist():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=300)
    issuer: str
    authority_level: int = Field(ge=1, le=5)
    doc_type: Literal["regulation", "circular", "notice", "faq", "handbook", "unofficial"]
    version: str
    effective_from: date
    effective_to: date | None = None
    supersedes: str = ""
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    provenance: str
    retrieved_on: date
    synthetic: Literal["Y", "N"]

    @model_validator(mode="before")
    @classmethod
    def empty_end_date(cls, value):
        if isinstance(value, dict) and value.get("effective_to") == "":
            value = dict(value, effective_to=None)
        return value

    @model_validator(mode="after")
    def check_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")
        return self


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    as_of_date: date = Field(default_factory=today_ist)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["policy", "attendance", "exam_eligibility", "placement_eligibility", "results"]
    course_code: str | None = Field(default=None, max_length=30)
    hypothetical_clear_backlogs: bool = False


class Citation(BaseModel):
    doc_id: str
    title: str
    section: str
    page: int
    version: str
    effective_from: str


class Answer(BaseModel):
    trace_id: str
    answer: str
    answer_type: Literal["retrieved_fact", "calculated", "not_found", "clarification_needed", "refused", "conflict_flagged"]
    citations: list[Citation] = Field(default_factory=list)
    tools_invoked: list[dict] = Field(default_factory=list)
    applied_rules: list[dict] = Field(default_factory=list)
    conflicts_detected: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    explanation: str = ""
    as_of_date: str
