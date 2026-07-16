from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from threading import RLock
from urllib.parse import quote, unquote


KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
SUPPORTED_SUFFIXES = {".json", ".md", ".txt", ".yaml", ".yml"}
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]*", re.IGNORECASE)
MAX_CHUNK_CHARS = 4_000


@dataclass(frozen=True)
class Document:
    path: str
    title: str
    media_type: str
    content: str


@dataclass(frozen=True)
class Chunk:
    document: Document
    heading: str
    content: str
    terms: Counter[str]


def _tokenize(value: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(value)]


def _media_type(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "application/json"
    if path.suffix.lower() == ".md":
        return "text/markdown"
    if path.suffix.lower() in {".yaml", ".yml"}:
        return "application/yaml"
    return "text/plain"


def _title(path: Path, content: str) -> str:
    if path.suffix.lower() == ".md":
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return path.stem.replace("_", " ").replace("-", " ").title()


def _split_document(document: Document) -> list[Chunk]:
    sections: list[tuple[str, list[str]]] = []
    heading = document.title
    lines: list[str] = []
    for line in document.content.splitlines():
        if line.startswith("#") and line.lstrip("#").startswith(" "):
            if lines:
                sections.append((heading, lines))
            heading = line.lstrip("# ").strip() or document.title
            lines = [line]
        else:
            lines.append(line)
    if lines:
        sections.append((heading, lines))

    chunks: list[Chunk] = []
    for section_heading, section_lines in sections or [(heading, [document.content])]:
        section = "\n".join(section_lines).strip()
        for start in range(0, len(section), MAX_CHUNK_CHARS):
            content = section[start : start + MAX_CHUNK_CHARS].strip()
            if content:
                searchable = f"{document.path} {section_heading} {content}"
                chunks.append(
                    Chunk(document, section_heading, content, Counter(_tokenize(searchable)))
                )
    return chunks


class KnowledgeIndex:
    def __init__(self, root: Path = KNOWLEDGE_DIR) -> None:
        self.root = root
        self._lock = RLock()
        self._fingerprint: tuple[tuple[str, int, int], ...] = ()
        self._documents: dict[str, Document] = {}
        self._chunks: list[Chunk] = []
        self._document_frequency: Counter[str] = Counter()

    def _files(self) -> list[Path]:
        return sorted(
            path
            for path in self.root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )

    def _current_fingerprint(self, files: list[Path]) -> tuple[tuple[str, int, int], ...]:
        return tuple(
            (
                path.relative_to(self.root).as_posix(),
                path.stat().st_mtime_ns,
                path.stat().st_size,
            )
            for path in files
        )

    def refresh(self, force: bool = False) -> bool:
        with self._lock:
            files = self._files()
            fingerprint = self._current_fingerprint(files)
            if not force and fingerprint == self._fingerprint:
                return False

            documents: dict[str, Document] = {}
            chunks: list[Chunk] = []
            for path in files:
                relative_path = path.relative_to(self.root).as_posix()
                content = path.read_text(encoding="utf-8")
                if path.suffix.lower() == ".json":
                    content = json.dumps(json.loads(content), indent=2, ensure_ascii=True)
                document = Document(
                    path=relative_path,
                    title=_title(path, content),
                    media_type=_media_type(path),
                    content=content,
                )
                documents[relative_path] = document
                chunks.extend(_split_document(document))

            document_frequency: Counter[str] = Counter()
            for chunk in chunks:
                document_frequency.update(chunk.terms.keys())

            self._fingerprint = fingerprint
            self._documents = documents
            self._chunks = chunks
            self._document_frequency = document_frequency
            return True

    def documents(self) -> list[Document]:
        self.refresh()
        return list(self._documents.values())

    def get(self, encoded_path: str) -> Document:
        self.refresh()
        path = unquote(encoded_path)
        try:
            return self._documents[path]
        except KeyError as exc:
            raise ValueError(f"Unknown knowledge document: {path}") from exc

    def search(self, query: str, limit: int = 5) -> list[tuple[float, Chunk]]:
        self.refresh()
        query_terms = Counter(_tokenize(query))
        if not query_terms:
            return []

        total_chunks = max(len(self._chunks), 1)
        ranked: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            score = 0.0
            for term, query_count in query_terms.items():
                term_count = chunk.terms.get(term, 0)
                if not term_count:
                    continue
                inverse_frequency = math.log(
                    1 + total_chunks / (1 + self._document_frequency[term])
                )
                score += query_count * (1 + math.log(term_count)) * inverse_frequency
            if score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[: max(1, min(limit, 10))]

    def catalog(self) -> str:
        entries = [
            {
                "title": document.title,
                "path": document.path,
                "uri": f"toku://knowledge/{quote(document.path, safe='')}",
                "media_type": document.media_type,
            }
            for document in self.documents()
        ]
        return json.dumps({"documents": entries}, indent=2)


INDEX = KnowledgeIndex()


def register(mcp) -> None:
    @mcp.resource("toku://knowledge/catalog", mime_type="application/json")
    def knowledge_catalog() -> str:
        """List all currently indexed TokuEyes knowledge documents."""
        return INDEX.catalog()

    @mcp.resource("toku://knowledge/{document}")
    def knowledge_document(document: str) -> str:
        """Read one knowledge document using its encoded catalog path."""
        return INDEX.get(document).content

    @mcp.tool()
    def search_knowledge(query: str, limit: int = 5) -> str:
        """Look up grounded facts about TokuEyes AI models, systems, and infrastructure.

        Call this for ANY question that asks what something IS or does — e.g.
        "what is r model", "what is m model", "explain qc2", "tell me about the
        cvd model", "how does hba1c_model work". These are knowledge-base lookups
        against files like r_model.md, m_model.md, cvd_model.md, qc_model.md, etc.
        under knowledge/models/.

        The index refreshes automatically when supported files are added, changed,
        or removed under the server's knowledge directory.
        """
        matches = INDEX.search(query, limit)
        if not matches:
            return json.dumps(
                {
                    "query": query,
                    "matches": [],
                    "message": "No grounded context was found in the knowledge corpus.",
                },
                indent=2,
            )
        return json.dumps(
            {
                "query": query,
                "matches": [
                    {
                        "source": match.document.path,
                        "title": match.document.title,
                        "heading": match.heading,
                        "score": round(score, 4),
                        "content": match.content,
                    }
                    for score, match in matches
                ],
            },
            indent=2,
        )

    @mcp.tool()
    def refresh_knowledge_index() -> str:
        """Force the server to rebuild its knowledge index from disk."""
        changed = INDEX.refresh(force=True)
        return json.dumps(
            {"refreshed": changed, "document_count": len(INDEX.documents())}
        )

    @mcp.prompt()
    def answer_from_knowledge(question: str) -> str:
        """Prepare a grounded answer to a TokuEyes system or model question."""
        context = search_knowledge(question, limit=5)
        return (
            "Answer the user's question using only the supplied TokuEyes context. "
            "Cite each factual section with its source path. If the context is "
            "insufficient, say what is missing instead of guessing.\n\n"
            f"Question:\n{question}\n\nContext:\n{context}"
        )