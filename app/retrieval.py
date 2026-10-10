"""Document ingestion and persistent search, with citation metadata kept intact."""
import hashlib
import io
import json
import re
import threading

from .models import Source

# These patterns parse supported policy statements; they never execute document instructions.
RULE_PATTERNS = {
    "min_attendance_pct": (r"minimum attendance(?: required)?(?: is|:)?\s*(\d+(?:\.\d+)?)\s*%", ">="),
    "min_cgpa": (r"minimum CGPA(?: required)?(?: is|:)?\s*(\d+(?:\.\d+)?)", ">="),
    "max_backlogs": (r"maximum active backlogs(?: allowed)?(?: is|:)?\s*(\d+)", "<="),
    "pass_mark": (r"minimum pass mark(?: is|:)?\s*(\d+(?:\.\d+)?)", ">="),
}


class Embedder:
    def __init__(self, backend):
        self.backend = backend
        self.model = None

    def encode(self, texts):
        if self.backend == "hash":
            # Explicit test-only adapter; it is not a semantic embedding model.
            import numpy as np
            result = []
            for text in texts:
                vector = np.zeros(384, dtype=float)
                for word in re.findall(r"[a-z0-9]+", text.lower()):
                    index = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 384
                    vector[index] += 1
                norm = np.linalg.norm(vector)
                result.append((vector / norm if norm else vector).tolist())
            return result
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return self.model.encode(texts, normalize_embeddings=True).tolist()


def split_document(content, filename, doc_id):
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(io.BytesIO(content)).pages)]
    elif filename.lower().endswith((".md", ".txt")):
        pages = [(1, content.decode("utf-8"))]
    else:
        raise ValueError("Use a selectable-text PDF, Markdown, or UTF-8 text file.")
    chunks = []
    section = "Document text"
    for page, text in pages:
        if not text.strip():
            raise ValueError(f"Page {page} has no extractable text; OCR is not included in this MVP.")
        blocks = re.split(r"\n(?=#{1,6}\s|\d+\.\d+\s)", text)
        for block in blocks:
            lines = block.strip().splitlines()
            if not lines:
                continue
            if lines[0].startswith("#") or re.match(r"\d+\.\d+\s", lines[0]):
                section = lines[0].lstrip("# ").strip()
                number = re.match(r"\d+(?:\.\d+)*\b", section)
                if number:
                    section = number[0]
            words = block.split()
            for offset in range(0, len(words), 110):
                passage = " ".join(words[offset:offset + 140])
                chunks.append({"chunk_id": f"{doc_id}-{len(chunks)}", "doc_id": doc_id,
                               "section": section, "page": page, "text": passage})
    if not chunks:
        raise ValueError("The document is empty.")
    return chunks


class KnowledgeBase:
    def __init__(self, db, settings):
        import chromadb
        self.db = db
        self.settings = settings
        self.lock = threading.RLock()
        self.embedder = Embedder(settings.embedding_backend)
        self.client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
        # Different adapters use different collections; never mix their vectors.
        self.collection = self.client.get_or_create_collection(
            f"policies_{settings.embedding_backend}", metadata={"hnsw:space": "cosine"})

    def ingest(self, content: bytes, filename: str, source: Source):
        metadata = source.model_dump(mode="json")
        digest = hashlib.sha256(content + json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        with self.lock:
            existing = self.db.rows("SELECT digest FROM sources WHERE doc_id = ?", (source.doc_id,))
            if existing:
                if existing[0]["digest"] != digest:
                    raise ValueError("doc_id already exists. Use a new document ID for a new version.")
                saved = self.db.rows("SELECT * FROM chunks WHERE doc_id=?", (source.doc_id,))
                indexed = self.collection.get(where={"doc_id": source.doc_id})["ids"]
                if len(indexed) != len(saved):
                    self.collection.upsert(ids=[x["chunk_id"] for x in saved],
                                           embeddings=self.embedder.encode([x["text"] for x in saved]),
                                           documents=[x["text"] for x in saved],
                                           metadatas=[{"doc_id": source.doc_id, "section": x["section"], "page": x["page"]} for x in saved])
                return {"doc_id": source.doc_id, "chunks_indexed": len(saved), "status": "already_indexed"}
            chunks = split_document(content, filename, source.doc_id)
            vectors = self.embedder.encode([x["text"] for x in chunks])
            rules = []
            for chunk in chunks:
                for parameter, (pattern, operator) in RULE_PATTERNS.items():
                    match = re.search(pattern, chunk["text"], re.I)
                    if match:
                        if re.search(r"ignore.*instructions|system prompt|bypass.*(?:rule|safety)|reveal.*secret", chunk["text"], re.I):
                            raise ValueError("Instruction-like content in a numeric rule requires review; no changes were published.")
                        value = float(match[1])
                        limit = 10 if parameter == "min_cgpa" else 100
                        if not 0 <= value <= limit:
                            raise ValueError(f"Invalid {parameter} value")
                        rule_id = f"{chunk['chunk_id']}-{parameter}"
                        rules.append((rule_id, match[0], parameter, operator, match[1],
                                      source.scope_programmes, source.scope_batches,
                                      str(source.effective_from), str(source.effective_to or ""),
                                      source.doc_id, chunk["section"]))
            # An unsupported amendment must not publish while calculators keep an old rule.
            if source.supersedes:
                targets = [x.strip() for x in source.supersedes.split(";") if x.strip()]
                old_parameters = set()
                for target in targets:
                    parts = target.split("#", 1)
                    query = "SELECT parameter FROM rule_registry WHERE source_doc_id=?"
                    values = [parts[0]]
                    if len(parts) == 2:
                        query += " AND source_section=?"
                        values.append(parts[1])
                    old_parameters.update(r["parameter"] for r in self.db.rows(query, tuple(values)))
                new_parameters = {r[2] for r in rules}
                if old_parameters - new_parameters:
                    raise ValueError("Unsupported rule amendment: extraction did not find all replaced numeric parameters. Upload a supported, reviewed clause; no changes were published.")
            try:
                # Queries use the same lock. A partially indexed document is never visible.
                self.collection.upsert(ids=[x["chunk_id"] for x in chunks], embeddings=vectors,
                                       documents=[x["text"] for x in chunks],
                                       metadatas=[{"doc_id": source.doc_id, "section": x["section"], "page": x["page"]} for x in chunks])
                with self.db.connect() as conn:
                    conn.execute("INSERT INTO sources VALUES (?, ?, ?)", (source.doc_id, json.dumps(metadata), digest))
                    conn.executemany("INSERT INTO chunks VALUES (:chunk_id,:doc_id,:section,:page,:text)", chunks)
                    conn.executemany("INSERT INTO rule_registry VALUES (?,?,?,?,?,?,?,?,?,?,?)", rules)
            except Exception:
                self.collection.delete(where={"doc_id": source.doc_id})
                raise
            return {"doc_id": source.doc_id, "chunks_indexed": len(chunks), "status": "indexed", "rules_registered": len(rules)}

    def search(self, question, as_of, student, top_k=5):
        from .rules import applicable
        with self.lock:
            sources = {s["doc_id"]: s for s in self.db.sources() if applicable(s, as_of, student)}
            if not sources or not self.collection.count():
                return []
            # Filter applicability before top-k so future/inapplicable sources cannot crowd it out.
            result = self.collection.query(query_embeddings=self.embedder.encode([question]),
                                           n_results=min(top_k, self.collection.count()),
                                           where={"doc_id": {"$in": list(sources)}},
                                           include=["documents", "metadatas", "distances"])
            return [{"text": text, **meta, "source": sources[meta["doc_id"]], "score": round(1 - distance, 4)}
                    for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])]
