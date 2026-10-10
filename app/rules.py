"""Policy precedence is code, not an LLM's opinion."""
from datetime import date


class RuleConflict(Exception):
    def __init__(self, candidates):
        self.candidates = candidates


def in_scope(scope, value, is_batch=False):
    if scope == "ALL":
        return True
    if value is None:
        return False
    for item in scope.split(";"):
        item = item.strip()
        if is_batch and item.endswith("+") and item[:-1].isdigit():
            if int(value) >= int(item[:-1]):
                return True
        elif item == str(value):
            return True
    return False


def applicable(source, as_of, student):
    return (
        source["effective_from"] <= as_of
        and (not source.get("effective_to") or source["effective_to"] >= as_of)
        and in_scope(source["scope_programmes"], student.get("programme"))
        and in_scope(source["scope_batches"], student.get("batch_year"), True)
    )


def choose(candidates):
    """Caller already filtered date and scope. Apply Annex A steps 2-5."""
    if not candidates:
        return None
    removed = set()
    for new in candidates:
        if new["source"]["authority_level"] > 2:
            continue
        targets = [x.strip() for x in new["source"].get("supersedes", "").split(";")]
        for old in candidates:
            old_doc = old["source"]["doc_id"]
            if new is not old and (old_doc in targets or f"{old_doc}#{old['section']}" in targets):
                removed.add(old["id"])
    remaining = [x for x in candidates if x["id"] not in removed]
    if not remaining:
        raise RuleConflict(candidates)  # A circular supersession cycle is not a winner.
    authority = min(x["source"]["authority_level"] for x in remaining)
    remaining = [x for x in remaining if x["source"]["authority_level"] == authority]
    latest = max(x["source"]["effective_from"] for x in remaining)
    remaining = [x for x in remaining if x["source"]["effective_from"] == latest]
    values = {x["value"] for x in remaining}
    if len(values) > 1:
        raise RuleConflict(remaining)
    return sorted(remaining, key=lambda x: x["id"])[0]


def resolve(db, parameter, as_of, student):
    sources = {s["doc_id"]: s for s in db.sources()}
    rows = db.rows("SELECT * FROM rule_registry WHERE parameter = ?", (parameter,))
    candidates = []
    for row in rows:
        source = sources[row["source_doc_id"]]
        if source["authority_level"] == 5 or not applicable(source, as_of, student):
            continue
        if not in_scope(row["scope_programmes"], student.get("programme")):
            continue
        if not in_scope(row["scope_batches"], student.get("batch_year"), True):
            continue
        if row["effective_from"] > as_of or (row["effective_to"] and row["effective_to"] < as_of):
            continue
        candidates.append(dict(row, id=row["rule_id"], section=row["source_section"], source=source))
    winner = choose(candidates)
    conflicts = []
    if winner:
        conflicts = [{"parameter": parameter, "winner": winner["rule_id"],
                      "sources_considered": [x["source_doc_id"] for x in candidates],
                      "resolution": "Applicability, explicit supersession, authority, then effective date."}]
        if len(candidates) < 2:
            conflicts = []
    return winner, conflicts
