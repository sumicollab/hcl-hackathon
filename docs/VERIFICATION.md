# Verification of the first MVP

Verified on 10 October 2026 using Python 3.12 on Windows.

| Check | Result | Actual scope |
|---|---|---|
| Python compilation | Passed | All Python files parse |
| Dependency consistency | Passed | `pip check` found no broken requirements |
| Automated checks | 18 passed | Mock LLM, test-only hash embeddings, actual Chroma/SQLite/LangGraph/FastAPI; includes Streamlit form-to-API flow |
| Development data validation | Passed | 30 students, 6 courses, 90 attendance rows and 90 result rows; no reported logical violations |
| Actual MiniLM model | Loaded and indexed | Nine sample document chunks, five supported numeric rules |
| Development benchmark | 22/22 passed | Actual MiniLM + Chroma retrieval, mock LLM; expected type, answer substring and expected source-document presence |
| Browser preview | Not verified | Loopback connections timed out in this execution environment |
| Docker startup | Not verified | Docker executable unavailable |
| Actual Ollama inference | Not verified | Ollama executable/model unavailable |

The benchmark used the in-process ASGI API after network connections to local servers timed out. Its exact report is `evaluation/development_report.json`. It is not a measured LLM accuracy or citation-support score. Fast mock latency does not predict local-model latency. Real-model evaluation and a Docker smoke test remain required on the team's machine.

Policies and seeded data are explicitly synthetic development fixtures. They are not a compliant official university source corpus or the required LLM-generated submission dataset.
