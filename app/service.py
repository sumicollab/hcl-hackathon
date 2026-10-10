"""A bounded LangGraph workflow: guard, plan, answer, then audit."""
import json
import re
import time
import uuid
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from .llm import LocalLLM
from .models import Answer, Citation, Plan
from .rules import RuleConflict, resolve

NOT_FOUND = "I could not find this information in the authorised university sources."


class State(TypedDict, total=False):
    question: str
    student_id: str | None
    as_of: str
    trace_id: str
    plan: dict
    response: dict
    evidence: list
    model_usage: dict


def citation(source, section, page):
    return Citation(doc_id=source["doc_id"], title=source["title"], section=section,
                    page=page, version=source["version"], effective_from=source["effective_from"])


class Assistant:
    def __init__(self, db, knowledge, settings):
        self.db, self.knowledge, self.settings = db, knowledge, settings
        graph = StateGraph(State)
        graph.add_node("guard", self.guard)
        graph.add_node("plan", self.plan)
        graph.add_node("answer", self.answer)
        graph.add_edge(START, "guard")
        graph.add_conditional_edges("guard", lambda s: "stop" if s.get("response") else "continue",
                                    {"stop": END, "continue": "plan"})
        graph.add_edge("plan", "answer")
        graph.add_edge("answer", END)
        self.graph = graph.compile()

    def response(self, state, answer, kind, **kwargs):
        return Answer(trace_id=state["trace_id"], answer=answer, answer_type=kind,
                      as_of_date=state["as_of"], **kwargs).model_dump(mode="json")

    def guard(self, state):
        question = state["question"]
        requested = set(re.findall(r"\bS\d{4}\b", question, re.I))
        if any(x.upper() != state.get("student_id") for x in requested):
            return {"response": self.response(state, "I cannot access another student's records.", "refused")}
        if re.search(r"ignore\s+(?:all\s+|previous\s+)?instructions|system prompt|reveal.*(?:password|secret)|drop table", question, re.I):
            return {"response": self.response(state, "I cannot follow requests to bypass access or safety controls.", "refused")}
        return {}

    def plan(self, state):
        llm = LocalLLM(self.settings)
        plan = llm.plan(state["question"])
        return {"plan": plan.model_dump(), "model_usage": {"calls": llm.calls, "tokens": llm.tokens}}

    def answer(self, state):
        with self.knowledge.lock:
            return self._answer(state)

    def _answer(self, state):
        plan = Plan.model_validate(state["plan"])
        student = self.db.student(state["student_id"]) if state.get("student_id") else None
        if plan.action != "policy":
            if not student:
                return {"response": self.response(state, "An authorised student identity is required for personal records.", "refused")}
            return self.personal(state, plan, student)
        evidence = self.knowledge.search(state["question"], state["as_of"], student or {})
        evidence = [p for p in evidence if not re.search(r"ignore.*instructions|system prompt|reveal.*secret", p["text"], re.I)]
        # For supported numeric policies, inspect ALL applicable registry entries, not just top-k.
        parameter = self.policy_parameter(state["question"])
        if parameter:
            try:
                winner, conflicts = resolve(self.db, parameter, state["as_of"], student or {})
            except RuleConflict as conflict:
                return self.conflict_response(state, conflict)
            if winner:
                chunk = self.rule_chunk(winner)
                upcoming = self.upcoming(parameter, state["as_of"], student or {})
                answer = f"The applicable {parameter.replace('_', ' ')} is {winner['value']}."
                if upcoming:
                    answer += " Upcoming changes exist and are not applied to this date."
                return {"response": self.response(state, answer, "retrieved_fact",
                        citations=[citation(winner["source"], winner["source_section"], chunk["page"])],
                        applied_rules=[self.public_rule(winner)], conflicts_detected=conflicts,
                        explanation=chunk["text"]), "evidence": evidence}
        llm = LocalLLM(self.settings)
        selected = llm.evidence(state["question"], evidence)
        indices = list(dict.fromkeys(selected.evidence_indices))
        if not selected.supported or not indices or any(i < 0 or i >= len(evidence) for i in indices):
            return {"response": self.response(state, NOT_FOUND, "not_found"), "evidence": evidence,
                    "model_usage": self.usage(state, llm)}
        passages = [evidence[i] for i in indices]
        # Only relevant selected evidence can trigger procedural conflict review.
        competing = [p for p in passages if p["source"].get("supersedes")]
        if competing:
            return {"response": self.response(state, "A related amendment exists. This MVP cannot safely resolve this procedure; contact the issuing office.",
                                               "conflict_flagged", citations=[citation(p["source"], p["section"], p["page"]) for p in passages]),
                    "evidence": evidence, "model_usage": self.usage(state, llm)}
        # Factual answer is verbatim evidence. Model explanation is separately labelled.
        return {"response": self.response(state, "\n\n".join(p["text"] for p in passages), "retrieved_fact",
                                          citations=[citation(p["source"], p["section"], p["page"]) for p in passages],
                                          explanation=selected.explanation), "evidence": evidence,
                "model_usage": self.usage(state, llm)}

    @staticmethod
    def policy_parameter(question):
        text = question.lower()
        if "attendance" in text:
            return "min_attendance_pct"
        if "cgpa" in text:
            return "min_cgpa"
        if "backlog" in text:
            return "max_backlogs"
        if "pass mark" in text:
            return "pass_mark"
        return None

    def rule_chunk(self, rule):
        return self.db.rows("SELECT * FROM chunks WHERE doc_id=? AND section=? ORDER BY page LIMIT 1",
                            (rule["source_doc_id"], rule["source_section"]))[0]

    @staticmethod
    def public_rule(rule):
        return {k: rule[k] for k in ["rule_id", "parameter", "operator", "value", "source_doc_id", "source_section"]}

    def upcoming(self, parameter, as_of, student):
        from .rules import in_scope
        sources = {s["doc_id"]: s for s in self.db.sources()}
        return [r for r in self.db.rows("SELECT * FROM rule_registry WHERE parameter=? AND effective_from>?", (parameter, as_of))
                if sources[r["source_doc_id"]]["authority_level"] < 5
                and in_scope(r["scope_programmes"], student.get("programme"))
                and in_scope(r["scope_batches"], student.get("batch_year"), True)]

    def conflict_response(self, state, conflict):
        refs = [citation(r["source"], r["source_section"], self.rule_chunk(r)["page"]) for r in conflict.candidates]
        return {"response": self.response(state, "The applicable sources conflict. Contact the issuing office.", "conflict_flagged",
                                          citations=refs, conflicts_detected=[{"rule_ids": [r["rule_id"] for r in conflict.candidates]}])}

    def personal(self, state, plan, student):
        tools, rules, conflicts, refs, assumptions = [], [], [], [], []
        if plan.action in {"attendance", "exam_eligibility", "results"} and not plan.course_code:
            return {"response": self.response(state, "Which course code do you mean?", "clarification_needed")}
        if plan.action in {"attendance", "exam_eligibility"}:
            rows = self.db.rows("SELECT classes_held, classes_attended FROM attendance WHERE student_id=? AND course_code=?",
                                (state["student_id"], plan.course_code))
            if not rows:
                return {"response": self.response(state, NOT_FOUND, "not_found")}
            record = rows[0]
            pct = record["classes_attended"] * 100 / record["classes_held"]
            result = dict(record, attendance_pct=round(pct, 2), course_code=plan.course_code)
            tools.append({"tool": "get_attendance", "input": {"course_code": plan.course_code}, "output": result.copy()})
            if plan.action == "exam_eligibility":
                parameters = ["min_attendance_pct"]
            else:
                parameters = []
        elif plan.action == "results":
            rows = self.db.rows("SELECT course_code, exam_session, exam_type, total_marks, max_marks, result FROM results WHERE student_id=? AND course_code=?",
                                (state["student_id"], plan.course_code))
            if not rows:
                return {"response": self.response(state, NOT_FOUND, "not_found")}
            result = {"records": rows}
            parameters = []
            tools.append({"tool": "get_results", "input": {"course_code": plan.course_code}, "output": result.copy()})
        else:
            result = {"cgpa": student["cgpa"], "active_backlogs": student["active_backlogs"]}
            parameters = ["min_cgpa", "max_backlogs"]
            if plan.hypothetical_clear_backlogs:
                result["active_backlogs"] = 0
                assumptions.append("Hypothetical: all active backlogs cleared; CGPA held unchanged. Actual records are not modified.")
            tools.append({"tool": "get_placement_profile", "input": {}, "output": result.copy()})
        try:
            for parameter in parameters:
                winner, detected = resolve(self.db, parameter, state["as_of"], student)
                if not winner:
                    return {"response": self.response(state, NOT_FOUND, "not_found", tools_invoked=tools)}
                rules.append(self.public_rule(winner))
                conflicts.extend(detected)
                chunk = self.rule_chunk(winner)
                refs.append(citation(winner["source"], winner["source_section"], chunk["page"]))
            if parameters:
                if plan.action == "exam_eligibility":
                    # Cross multiplication avoids rounding a boundary case into eligibility.
                    threshold = float(rules[0]["value"])
                    passed = record["classes_attended"] * 100 >= record["classes_held"] * threshold
                    result["result"] = "ATTENDANCE_REQUIREMENT_MET" if passed else "ATTENDANCE_REQUIREMENT_NOT_MET"
                    assumptions.append("This MVP checks the documented attendance requirement only; it does not certify all exam conditions.")
                else:
                    values = {r["parameter"]: float(r["value"]) for r in rules}
                    passed = result["cgpa"] >= values["min_cgpa"] and result["active_backlogs"] <= values["max_backlogs"]
                    result["result"] = "PROFILE_REQUIREMENTS_MET" if passed else "PROFILE_REQUIREMENTS_NOT_MET"
                    assumptions.append("Checks CGPA and backlog conditions only; employer-specific requirements are outside this MVP.")
                tools.append({"tool": plan.action, "input": {"course_code": plan.course_code}, "output": result.copy()})
        except RuleConflict as conflict:
            return self.conflict_response(state, conflict)
        llm = LocalLLM(self.settings)
        explanation = llm.explain_calculation(state["question"], result)
        return {"response": self.response(state, json.dumps(result, ensure_ascii=False), "calculated", citations=refs,
                                          tools_invoked=tools, applied_rules=rules, conflicts_detected=conflicts,
                                          assumptions=assumptions, explanation=explanation),
                "model_usage": self.usage(state, llm)}

    @staticmethod
    def usage(state, llm):
        old = state.get("model_usage", {})
        return {"calls": old.get("calls", 0) + llm.calls, "tokens": old.get("tokens", 0) + llm.tokens}

    def ask(self, request, student_id):
        start = time.perf_counter()
        state = self.graph.invoke({"question": request.question, "student_id": student_id,
                                   "as_of": str(request.as_of_date), "trace_id": uuid.uuid4().hex[:16]})
        result = Answer.model_validate(state["response"]).model_dump(mode="json")
        usage = state.get("model_usage", {"calls": 0, "tokens": 0})
        record = {"trace_id": result["trace_id"], "timestamp": datetime.now(timezone.utc).isoformat(),
                  "answer_type": result["answer_type"], "sources_retrieved": [
                      {"doc_id": p["doc_id"], "section": p["section"], "score": p["score"]} for p in state.get("evidence", [])],
                  "sources_applied": result["citations"],
                  "tools_invoked": result["tools_invoked"], "rules_applied": result["applied_rules"],
                  "conflicts_detected": result["conflicts_detected"], "model": "mock" if self.settings.mock_llm else self.settings.ollama_model,
                  "embedding_backend": self.settings.embedding_backend, "llm_calls": usage["calls"], "tokens": usage["tokens"],
                  "latency_ms": round((time.perf_counter() - start) * 1000, 2)}
        # Raw question and student name are deliberately not stored in audit logs.
        self.db.audit(result["trace_id"], student_id, record)
        return result
