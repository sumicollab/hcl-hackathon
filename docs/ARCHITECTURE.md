# Architecture explained for beginners

The assistant is an open-book help desk. The model reads the question, the library supplies evidence, and a calculator handles numbers.

| File | Job | Analogy |
|---|---|---|
| `ui.py` | Collect question and display the response | Help-desk counter |
| `app/main.py` | HTTP endpoints and validation boundary | Receptionist |
| `app/models.py` | Fixed field names, allowed values and types | Printed forms |
| `app/service.py` | Guard, plan, retrieve, calculate and record | Coordinator |
| `app/llm.py` | Local model requests and validated plans | Language assistant |
| `app/retrieval.py` | Extract text, create embeddings and search | Librarian |
| `app/storage.py` | Exact data in SQLite | Records cabinet |
| `app/rules.py` | Decide which policy applies | Rulebook referee |
| `scripts/` | Prepare data and measure behavior | Setup and inspection crew |

## Reading the code

A function is a small named job. A class groups related jobs and their state. A dictionary carries named values like a filled form. Type hints describe the expected shape. Pydantic checks that shape at runtime. SQL queries select exact rows; placeholders keep supplied values separate from SQL instructions.

LangGraph's State is the shared case folder. A node is a function. An edge chooses the next function. Our graph has three nodes, not a network of autonomous agents: guard -> plan -> answer. The answer node performs a bounded sequence of retrieval and tools. Python creates the response and audit.

An embedding is a list of numbers representing text. MiniLM creates it. Chroma searches nearby lists. This finds likely relevant clauses; it does not decide authority. Rule precedence is a separate Python job.

## Follow one question

1. UI sends a question, date and demo identity.
2. API validates the form and ID format.
3. Guard rejects explicit cross-student IDs and obvious bypass attempts.
4. Model proposes an allowed action and optional course code.
5. The validated plan selects code, not arbitrary commands.
6. Tools read the context student's records.
7. Rule selector filters dates and scope, then applies supersession, authority and recency.
8. Python calculates the attendance percentage and requirement result.
9. The model explains the result. The authoritative JSON and assumptions stay separate.
10. Backend saves a trace and UI shows the result and citations.

## Explain the choices

"We use a small fixed LangGraph workflow because the required operations are known. We do not need several agents negotiating who should perform a calculation. Chroma retrieves text; SQLite stores exact records; Python applies rules. The local LLM interprets and explains. We evaluate each layer separately so a fluent answer cannot hide an incorrect calculation."
