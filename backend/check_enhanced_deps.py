from __future__ import annotations

import importlib.util
import json
import traceback


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    modules = {
        "chromadb": has_module("chromadb"),
        "sentence_transformers": has_module("sentence_transformers"),
        "beautifulsoup4": has_module("bs4"),
        "lxml": has_module("lxml"),
        "playwright": has_module("playwright"),
    }
    print(json.dumps(modules, ensure_ascii=False, indent=2))
    if modules["chromadb"] and modules["sentence_transformers"]:
        from app.rag import rag_status, rebuild_vector_index

        print("Current RAG config:")
        print(json.dumps(rag_status(), ensure_ascii=False, indent=2))
        print("Rebuilding vector RAG index...")
        try:
            print(json.dumps(rebuild_vector_index(), ensure_ascii=False, indent=2))
            print(json.dumps(rag_status(), ensure_ascii=False, indent=2))
        except Exception:
            print("Vector RAG index rebuild failed:")
            traceback.print_exc()
            print("The system can still use keyword RAG fallback.")
    else:
        print("Vector RAG dependencies are incomplete; keyword RAG fallback will be used.")


if __name__ == "__main__":
    main()
