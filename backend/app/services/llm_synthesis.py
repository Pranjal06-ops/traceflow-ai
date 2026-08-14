"""
LLM synthesis layer.

Design decision (docs/decisions.md): the LLM is used ONLY for two things -
(1) turning already-collected, structured evidence into readable prose, and
(2) proposing a remediation description in natural language. It is never
given raw DB/tool access and never asked to "figure out" facts - all facts
are computed deterministically upstream in investigation_engine.py and
passed in as a fixed evidence list. The prompt explicitly instructs the
model not to introduce facts beyond what's provided, and the fallback path
(no API key) proves the system doesn't depend on an LLM to function -
it degrades to a template, not a failure.
"""
from __future__ import annotations

import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("traceflow.llm")

settings = get_settings()

SYNTHESIS_SYSTEM_PROMPT = """You are assisting a data platform incident investigation.
You will be given a JSON list of EVIDENCE items collected by deterministic tools, and a
ranked list of CANDIDATE root causes with scores computed by a rule-based engine.

Rules:
- Do not invent facts, systems, dates, or numbers that are not present in the evidence.
- Write a concise root-cause explanation (2-4 sentences) that cites which evidence supports it.
- Then write a concise remediation recommendation (1-3 sentences), concrete enough to act on.
- Output strict JSON: {"root_cause_explanation": str, "remediation_description": str}
- If the evidence is too thin to explain confidently, say so plainly instead of guessing.
"""


def synthesize_root_cause(evidence: list[dict], candidates: list[dict]) -> dict:
    if not settings.LLM_ENABLED:
        return _template_fallback(evidence, candidates)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        user_payload = json.dumps({"evidence": evidence, "candidates": candidates}, default=str)

        resp = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=500,
            system=SYNTHESIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_payload}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        parsed = json.loads(text)
        return {
            "root_cause_explanation": parsed["root_cause_explanation"],
            "remediation_description": parsed["remediation_description"],
            "synthesis_method": "llm",
        }
    except Exception:  # noqa: BLE001
        logger.exception("LLM synthesis failed, falling back to template")
        result = _template_fallback(evidence, candidates)
        result["synthesis_method"] = "template_fallback_after_llm_error"
        return result


def _template_fallback(evidence: list[dict], candidates: list[dict]) -> dict:
    """
    Deterministic, template-based synthesis used when no LLM key is
    configured. This is intentionally plain - it exists so the system is
    fully functional and testable without any external API dependency.
    """
    if not candidates:
        return {
            "root_cause_explanation": (
                "No candidate root cause could be constructed from the available evidence."
            ),
            "remediation_description": "Insufficient evidence to propose a remediation.",
            "synthesis_method": "template",
        }

    top = candidates[0]
    supporting = [e["summary"] for e in evidence if e.get("source_tool") in top.get("supporting_tools", [])]
    explanation = (
        f"The strongest candidate is: {top['description']}. "
        f"This is supported by {len(supporting)} evidence item(s): "
        + "; ".join(supporting[:4]) + "."
    )
    remediation = top.get("suggested_remediation", "Review the linked evidence and determine a fix manually.")
    return {
        "root_cause_explanation": explanation,
        "remediation_description": remediation,
        "synthesis_method": "template",
    }
