"""Context builders and interpreter response parser."""

import json
import re

from loader import SOP
from prompts import MAX_CHARS_PER_SOP


# ── Context builders ─────────────────────────────────────────────────────────

def build_context_block(sops: list[SOP]) -> str:
    """Format retrieved SOPs into a <context> block (admin use)."""
    parts = []
    for sop in sops:
        body = sop.body
        if len(body) > MAX_CHARS_PER_SOP:
            body = body[:MAX_CHARS_PER_SOP] + "\n[truncated]"
        parts.append(f"--- {sop.id} | {sop.title} ---\n{body}")
    return "<context>\n" + "\n\n".join(parts) + "\n</context>"


def build_interpreter_input(question: str, candidates: list[dict]) -> str:
    """Build the lightweight input for Stage 1 interpreter."""
    lines = []
    for c in candidates:
        lines.append(f"- {c['id']} | {c['title']} | {c['summary']}")
    candidate_block = "\n".join(lines)
    return f"<candidates>\n{candidate_block}\n</candidates>\n\nUser question: {question}"


def build_single_context(sop: SOP) -> str:
    """Build a minimal <context> block for Prompt A (single SOP)."""
    body = sop.body
    if len(body) > MAX_CHARS_PER_SOP:
        body = body[:MAX_CHARS_PER_SOP] + "\n[truncated]"
    return f"<context>\n--- {sop.id} | {sop.title} ---\n{body}\n</context>"


def build_multi_context(sops: list[SOP]) -> str:
    """Build a <context> block for Prompt B (2-3 SOPs, hard-capped)."""
    parts = []
    for sop in sops[:3]:
        body = sop.body
        if len(body) > MAX_CHARS_PER_SOP:
            body = body[:MAX_CHARS_PER_SOP] + "\n[truncated]"
        parts.append(f"--- {sop.id} | {sop.title} ---\n{body}")
    return "<context>\n" + "\n\n".join(parts) + "\n</context>"


# ── Interpreter response parser ──────────────────────────────────────────────

def parse_interpreter_response(text: str) -> dict:
    """Parse the interpreter's JSON response, with fallback for malformed output."""
    text = text.strip()
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            result = json.loads(json_match.group())
            return {
                "primary_sop": result.get("primary_sop"),
                "secondary_sops": result.get("secondary_sops", [])[:2],
                "route": result.get("route", "A"),
                "confidence": result.get("confidence", "low"),
                "intent": result.get("intent", ""),
            }
        except json.JSONDecodeError:
            pass
    return {
        "primary_sop": None,
        "secondary_sops": [],
        "route": "A",
        "confidence": "low",
        "intent": "",
    }
