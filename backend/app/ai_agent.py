from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from .rag import context_text, retrieve
from .reporting import insight_lines


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_salary",
            "description": "读取系统已经计算好的薪资统计结果，返回整体、岗位、城市、经验和学历维度统计。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "enum": ["overall", "category", "city", "experience", "education"],
                    }
                },
                "required": ["dimension"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_docx_report",
            "description": "根据统计结果生成可导出的 Word 报告摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {"type": "string", "description": "报告重点，例如招聘预算、地区差异、岗位竞争力。"}
                },
                "required": ["focus"],
            },
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    if name == "analyze_salary":
        dimension = arguments.get("dimension", "overall")
        mapping = {
            "overall": analysis.get("overall", {}),
            "category": analysis.get("by_category", []),
            "city": analysis.get("by_city", []),
            "experience": analysis.get("by_experience", []),
            "education": analysis.get("by_education", []),
        }
        return {"dimension": dimension, "data": mapping.get(dimension, {})}
    if name == "generate_docx_report":
        return {"focus": arguments.get("focus", ""), "summary": insight_lines(analysis)}
    return {"error": f"unknown tool: {name}"}


def fallback_report(analysis: dict[str, Any], rag_context: str = "") -> str:
    base = "\n".join(insight_lines(analysis))
    if rag_context:
        return base + "\n\n已参考知识库口径：\n" + rag_context
    return base


def qwen_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, timeout: int = 60) -> dict[str, Any]:
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or QWEN_API_KEY
    if not api_key:
        raise RuntimeError("缺少 QWEN_API_KEY 或 DASHSCOPE_API_KEY，已切换为本地模板报告。")
    endpoint = (os.getenv("QWEN_BASE_URL") or QWEN_BASE_URL).rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": os.getenv("QWEN_MODEL") or QWEN_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Qwen API HTTP {exc.code}: {body}") from exc


def generate_ai_report(analysis: dict[str, Any], user_goal: str = "生成行业薪酬洞察报告") -> dict[str, Any]:
    query = json.dumps(
        {
            "goal": user_goal,
            "overall": analysis.get("overall"),
            "issues": analysis.get("issues"),
        },
        ensure_ascii=False,
    )
    rag_chunks = retrieve(query, top_k=3)
    rag_context = context_text(rag_chunks)
    system = (
        "你是行业薪酬洞察AI智能体。必须遵守以下规则："
        "1. 只引用工具返回、用户提供或RAG上下文中的事实；"
        "2. 不得编造样本量、薪资数值、城市、岗位、公司名称或数据来源；"
        "3. 如果样本量不足或上下文没有依据，必须明确写出风险边界；"
        "4. 输出中文，结构固定为：样本说明、关键发现、企业建议、风险提示、数据口径；"
        "5. 工具调用只能使用函数定义中的参数，不得额外虚构参数。"
    )
    user = {
        "goal": user_goal,
        "available_summary": {
            "total": analysis.get("total"),
            "valid": analysis.get("valid"),
            "parse_accuracy": analysis.get("parse_accuracy"),
            "overall": analysis.get("overall"),
        },
        "rag_context": rag_context,
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]
    try:
        first = qwen_chat(messages, TOOLS)
        message = first["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            messages.append(message)
            for tool_call in tool_calls:
                fn = tool_call["function"]
                args = json.loads(fn.get("arguments") or "{}")
                result = call_tool(fn["name"], args, analysis)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": fn["name"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            second = qwen_chat(messages)
            text = second["choices"][0]["message"].get("content", "")
        else:
            text = message.get("content", "")
        return {"mode": "qwen_tool_calling", "text": text, "tool_calls": tool_calls, "rag_chunks": rag_chunks}
    except Exception as exc:
        return {"mode": "local_fallback", "text": fallback_report(analysis, rag_context), "error": str(exc), "rag_chunks": rag_chunks}
