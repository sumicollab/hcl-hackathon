# Synthetic data card to complete before submission

| Field | Fill after actual LLM generation |
|---|---|
| Purpose | Test policies, personal calculations, authorization and boundaries |
| Generator | Actual model/version, temperature and calls from generation_report.json |
| Prompts | Saved runtime/generated/prompt.txt; commit reviewed copies to the submission |
| Schema enforcement | Structured JSON, Pydantic parsing, SQLite constraints and validate_data.py |
| Counts/distributions | Record counts, programmes, batches, course coverage, attendance and results |
| Edge cases | List exact student/course pairs at boundaries, ABSENT, DETAINED and multiple backlogs |
| Validation | Preserve report, violations found and corrections |
| Model mistakes | Describe actual errors caught, not hypothetical ones |
| Known limits | State simplified distributions and missing cases |

Development data from seed_demo.py is deterministic Python-generated data. Do not claim it was produced by Ollama.
