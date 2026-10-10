# Five person ownership

| Person | Owns | Main files |
|---|---|---|
| 1 | Documents, sources, extraction and retrieval | `app/retrieval.py`, source documents/register |
| 2 | Synthetic data, tools and precedence | `app/storage.py`, `app/rules.py`, personal tools in `app/service.py`, data scripts |
| 3 | API, workflow, LLM and audit | `app/main.py`, `app/models.py`, `app/llm.py`, workflow in `app/service.py` |
| 4 | UI and API presentation | `ui.py` |
| 5 | Evaluation, tests, packaging and demo | `tests/`, `evaluation/`, evaluation script, Docker, README |

Person 2 and 3 share `service.py`: agree on edit boundaries before working concurrently. Everyone tests their component. Person 5 coordinates integration checks rather than being solely responsible for correctness.

First milestone: one question to one cited answer. Next: personal calculation. Next: a live circular changing the result. Then: privacy, uncertainty, conflicts, evaluation and rehearsal.

The guide says up to four participants. Confirm organizer approval for a five-person team. This document assigns implementation ownership; it does not assert competition eligibility or actual contributions.

Fill in actual names, Git commits, files changed, verification and AI assistance before submission.
