"""Person 4 owns this file: a small interface that calls the API."""
import json
import os
from datetime import date
import httpx
import streamlit as st
from app.presentation import answer_text

st.set_page_config(page_title="Campus Answers", page_icon="🎓", layout="wide")
api = os.getenv("API_URL", "http://localhost:8000")
st.title("🎓 Campus Answers")
st.caption("University Student Services · Evidence first · Calculations by Python")
with st.sidebar:
    st.header("Request context")
    student = st.text_input("Demo student ID", "S1001", help="Demo identity only. Real deployment needs authenticated sign-in.")
    as_of = st.date_input("Policy date", date(2026, 10, 10))
    st.info("Sample policies are synthetic development fixtures. Replace them with official university documents before judging.")
    try:
        health = httpx.get(api + "/health", timeout=5).json()
        st.caption(f"API: {health['status']} · LLM: {health['llm']}")
        if health["mock_llm"]:
            st.warning("Development mode: LLM is mocked. This is not a measured AI demo.")
        if health["embedding_backend"] == "hash":
            st.warning("Test-only hash retrieval is active.")
    except httpx.HTTPError:
        st.error("Start the backend first; see README.")

ask_tab, source_tab, ingest_tab = st.tabs(["Ask", "Sources", "Ingest document"])
with ask_tab:
    with st.form("question"):
        question = st.text_area("What would you like to know?", "Am I eligible for the CS201 exam?")
        submitted = st.form_submit_button("Find a supported answer", type="primary")
    if submitted:
        try:
            with st.spinner("Finding policies and checking records…"):
                response = httpx.post(api + "/ask", timeout=180,
                                      headers={"X-Student-Id": student} if student else {},
                                      json={"question": question, "as_of_date": as_of.isoformat()})
                response.raise_for_status()
                st.session_state["answer"] = response.json()
        except httpx.HTTPError as error:
            st.error(f"Request failed: {error}")
    result = st.session_state.get("answer")
    if result:
        st.subheader("Your answer")
        st.write(answer_text(result))
        if result["explanation"]:
            st.subheader("Explanation")
            st.write(result["explanation"])
        for assumption in result["assumptions"]:
            st.info(assumption)
        if result["citations"]:
            st.subheader("Supporting sources")
            for source in result["citations"]:
                st.write(f"• {source['title']} — Section {source['section']}, page {source['page']}; "
                         f"version {source['version']}, effective from {source['effective_from']}.")
        with st.expander("Tools, rules and conflicts"):
            st.caption(f"Trace: {result['trace_id']}")
            for tool in result["tools_invoked"]:
                st.write("Calculation used: " + tool["tool"].replace("_", " "))
            for rule in result["applied_rules"]:
                st.write(f"Applied rule: {rule['parameter'].replace('_', ' ')} "
                         f"{rule['operator']} {rule['value']} "
                         f"({rule['source_doc_id']}, section {rule['source_section']}).")
            st.write(f"Policy conflict records: {len(result['conflicts_detected'])}")

with source_tab:
    if st.button("Load source register"):
        try:
            r = httpx.get(api + "/sources", timeout=10)
            r.raise_for_status()
            st.dataframe(r.json(), hide_index=True)
        except httpx.HTTPError as error:
            st.error(str(error))

with ingest_tab:
    st.write("Add a new document version while the API is running.")
    st.caption("Supported: text PDF, Markdown and UTF-8 text. See docs/INGESTION.md for supported rule syntax.")
    token = st.text_input("Admin token", type="password")
    uploaded = st.file_uploader("Policy document", type=["pdf", "md", "txt"])
    metadata = st.text_area("Source Register metadata JSON", height=220)
    if st.button("Ingest") and uploaded:
        try:
            json.loads(metadata)
            r = httpx.post(api + "/ingest", timeout=180, headers={"X-Admin-Token": token},
                           files={"file": (uploaded.name, uploaded.getvalue())}, data={"metadata": metadata})
            r.raise_for_status()
            st.success("Document ingested")
            st.json(r.json())
        except (httpx.HTTPError, ValueError) as error:
            st.error(str(error))
