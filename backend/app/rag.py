from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT


KB_PATH = PROJECT_ROOT / "docs" / "rag_knowledge_base.md"
CHROMA_DIR = PROJECT_ROOT / "backend" / ".rag_chroma"
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
RAG_LOCAL_FILES_ONLY = os.getenv("RAG_LOCAL_FILES_ONLY", "1").lower() in {"1", "true", "yes", "on"}


DEFAULT_KB = """# 薪酬洞察知识库

## 薪资口径
月薪统一以 K/月表示。年薪表达如“24-36万年薪”应折算为月薪区间 20-30K/月。含“13薪”“14薪”的岗位保留发薪月数，并计算年薪估算。

## 样本量解释
当单个维度样本量低于 30 条时，应提示样本量有限，不宜作为企业定薪的唯一依据。

## 数据合规
只采集公开可访问岗位信息，不绕过登录、验证码、付费墙或访问限制，不采集求职者个人隐私数据。

## 岗位归一
BI分析师、商业分析师、数据运营可归入数据分析；Java后端、Python后端、服务端开发可归入后端开发；B端产品经理、数据产品经理可归入产品经理。

## 报告建议
薪酬建议应引用系统统计值，优先说明中位数、P75、P90 和样本量；不得编造未在统计结果中出现的城市、岗位或公司。
"""

_MODEL: Any | None = None
_VECTOR_READY = False
_VECTOR_ERROR = ""


def collection_name() -> str:
    safe_model = re.sub(r"[^A-Za-z0-9_]+", "_", EMBED_MODEL).strip("_").lower()
    safe_model = safe_model[-48:] if len(safe_model) > 48 else safe_model
    return f"salary_insight_kb_{safe_model or 'default'}"


def ensure_kb() -> None:
    if not KB_PATH.exists():
        KB_PATH.parent.mkdir(parents=True, exist_ok=True)
        KB_PATH.write_text(DEFAULT_KB, encoding="utf-8")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", text.lower())


def load_chunks() -> list[dict[str, str]]:
    ensure_kb()
    content = KB_PATH.read_text(encoding="utf-8")
    chunks: list[dict[str, str]] = []
    current_title = "知识库"
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current_lines:
                chunks.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = []
        elif line.strip() and not line.startswith("# "):
            current_lines.append(line)
    if current_lines:
        chunks.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return chunks


def chunk_hash(chunks: list[dict[str, str]]) -> str:
    raw = "\n".join(item["title"] + "\n" + item["content"] for item in chunks)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def keyword_retrieve(query: str, top_k: int = 3) -> list[dict[str, object]]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    scored = []
    qset = set(query_tokens)
    for chunk in load_chunks():
        tokens = tokenize(chunk["title"] + "\n" + chunk["content"])
        if not tokens:
            continue
        overlap = len(qset.intersection(tokens))
        density = overlap / math.sqrt(len(set(tokens)))
        if overlap:
            scored.append({**chunk, "score": round(density, 4), "retrieval": "keyword"})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]


def optional_imports() -> tuple[Any | None, Any | None]:
    try:
        import chromadb  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore

        return chromadb, SentenceTransformer
    except Exception:
        return None, None


def get_embedding_model() -> Any:
    global _MODEL
    if _MODEL is None:
        _, sentence_transformer = optional_imports()
        if sentence_transformer is None:
            raise RuntimeError("sentence-transformers 未安装，无法启用向量 RAG。")
        try:
            _MODEL = sentence_transformer(EMBED_MODEL, local_files_only=RAG_LOCAL_FILES_ONLY)
        except TypeError:
            _MODEL = sentence_transformer(EMBED_MODEL)
    return _MODEL


def vector_collection() -> Any:
    chromadb, _ = optional_imports()
    if chromadb is None:
        raise RuntimeError("chromadb 未安装，无法启用向量 RAG。")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(collection_name())


def rebuild_vector_index() -> dict[str, object]:
    chunks = load_chunks()
    model = get_embedding_model()
    collection = vector_collection()
    ids = [f"chunk-{idx}" for idx, _ in enumerate(chunks)]
    documents = [item["title"] + "\n" + item["content"] for item in chunks]
    embeddings = model.encode(documents, normalize_embeddings=True).tolist()
    metadatas = [
        {"title": item["title"], "content": item["content"], "kb_hash": chunk_hash(chunks)}
        for item in chunks
    ]
    try:
        collection.delete(ids=ids)
    except Exception:
        pass
    collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    return {"chunks": len(chunks), "kb_hash": chunk_hash(chunks), "model": EMBED_MODEL}


def vector_retrieve(query: str, top_k: int = 3) -> list[dict[str, object]]:
    collection = vector_collection()
    chunks = load_chunks()
    current_hash = chunk_hash(chunks)
    count = collection.count()
    if count != len(chunks):
        rebuild_vector_index()
    else:
        try:
            peek = collection.peek(limit=1)
            metadata = (peek.get("metadatas") or [{}])[0] or {}
            if metadata.get("kb_hash") != current_hash:
                rebuild_vector_index()
        except Exception:
            rebuild_vector_index()
    model = get_embedding_model()
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()[0]
    result = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    rows: list[dict[str, object]] = []
    for metadata, distance in zip(metadatas, distances):
        score = round(1 - float(distance), 4)
        rows.append(
            {
                "title": metadata.get("title", ""),
                "content": metadata.get("content", ""),
                "score": score,
                "retrieval": "vector",
            }
        )
    return rows


def retrieve(query: str, top_k: int = 3) -> list[dict[str, object]]:
    global _VECTOR_READY, _VECTOR_ERROR
    try:
        rows = vector_retrieve(query, top_k)
        _VECTOR_READY = True
        _VECTOR_ERROR = ""
        if rows:
            return rows
    except Exception as exc:
        _VECTOR_READY = False
        _VECTOR_ERROR = str(exc)
    return keyword_retrieve(query, top_k)


def rag_status() -> dict[str, object]:
    chromadb, sentence_transformer = optional_imports()
    return {
        "kb_path": str(KB_PATH),
        "chunks": len(load_chunks()),
        "vector_dependencies": bool(chromadb and sentence_transformer),
        "vector_ready": _VECTOR_READY,
        "vector_error": _VECTOR_ERROR,
        "embed_model": EMBED_MODEL,
        "local_files_only": RAG_LOCAL_FILES_ONLY,
        "collection": collection_name(),
        "chroma_dir": str(CHROMA_DIR),
    }


def context_text(chunks: list[dict[str, object]]) -> str:
    return "\n\n".join(f"【{item['title']}】\n{item['content']}" for item in chunks)
