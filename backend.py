"""
backend.py — RecapAI Meeting-Summarizer Backend
================================================
Drop-in replacement for the stub `fake_summarize` in app.py.

Supports two inference modes (set via RECAPAI_MODE env var):
  • "api"   — HuggingFace Inference API  (default, no GPU required)
  • "local" — local transformers pipeline (requires a CUDA/MPS GPU)

Usage in app.py
---------------
Replace:
    from backend import summarize_transcript as fake_summarize
Or simply:
    from backend import summarize_transcript
    ...
    result = summarize_transcript(transcript_text)

Environment variables (put in .env or export):
  RECAPAI_MODE          "api" (default) | "local"
  HF_API_TOKEN          HuggingFace token (required for "api" mode)
  RECAPAI_MODEL         model id (default: meta-llama/Llama-3.2-1B-Instruct)
  RECAPAI_MAX_TOKENS    max new tokens for generation (default: 1024)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # reads .env in project root

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_ID: str = os.getenv("RECAPAI_MODEL", "meta-llama/Llama-3.2-1B-Instruct")
MODE: str = os.getenv("RECAPAI_MODE", "api").lower()          # "api" | "local"
HF_TOKEN: str | None = os.getenv("HF_API_TOKEN")
MAX_NEW_TOKENS: int = int(os.getenv("RECAPAI_MAX_TOKENS", "1024"))

log = logging.getLogger("recapai.backend")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_EMPTY_RESULT: dict = {
    "summary": "",
    "decisions": [],
    "assigned_tasks": [],
    "open_questions": [],
}


def _validate_and_clean(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce raw LLM output into the agreed-upon schema.

    Guarantees the four expected keys exist with correct types, even if
    the model returns partial / malformed JSON.
    """
    result: dict[str, Any] = {}

    # --- summary ----------------------------------------------------------
    result["summary"] = str(raw.get("summary", "")).strip() or "(No summary produced.)"

    # --- decisions --------------------------------------------------------
    decisions = raw.get("decisions", [])
    if isinstance(decisions, str):
        decisions = [d.strip() for d in decisions.split("\n") if d.strip()]
    elif isinstance(decisions, list):
        decisions = [str(d).strip() for d in decisions if str(d).strip()]
    else:
        decisions = []
    result["decisions"] = decisions

    # --- assigned_tasks ---------------------------------------------------
    tasks_raw = raw.get("assigned_tasks", [])
    cleaned_tasks: list[dict[str, str]] = []
    if isinstance(tasks_raw, list):
        for t in tasks_raw:
            if isinstance(t, dict):
                cleaned_tasks.append({
                    "who":  str(t.get("who", "Unassigned")).strip(),
                    "what": str(t.get("what", "")).strip(),
                    "due":  str(t.get("due", "Not specified")).strip(),
                })
            elif isinstance(t, str) and t.strip():
                # Model sometimes returns plain strings — treat as task text
                cleaned_tasks.append({
                    "who":  "Unassigned",
                    "what": t.strip(),
                    "due":  "Not specified",
                })
    result["assigned_tasks"] = cleaned_tasks

    # --- open_questions ---------------------------------------------------
    oq = raw.get("open_questions", [])
    if isinstance(oq, str):
        oq = [q.strip() for q in oq.split("\n") if q.strip()]
    elif isinstance(oq, list):
        oq = [str(q).strip() for q in oq if str(q).strip()]
    else:
        oq = []
    result["open_questions"] = oq

    return result


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are RecapAI, a meeting-summarizer assistant.
Given a meeting transcript, extract ONLY a JSON object with these keys:

{
  "summary": "<concise paragraph summarizing the meeting>",
  "decisions": ["<decision 1>", "<decision 2>", ...],
  "assigned_tasks": [
    {"who": "<person>", "what": "<task description>", "due": "<deadline or 'Not specified'>"}, ...
  ],
  "open_questions": ["<unresolved question 1>", ...]
}

Rules:
- Output ONLY valid JSON. No markdown, no commentary, no extra text.
- If a field has no items, use an empty list [].
- For assigned_tasks, always include who, what, and due.
- Keep the summary concise (3-5 sentences).
- Decisions are concrete outcomes agreed upon.
- Open questions are items that were raised but NOT resolved.
"""


def _build_messages(transcript: str) -> list[dict[str, str]]:
    """Build the chat-style message list for the model."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Transcript:\n\n{transcript}"},
    ]


# ---------------------------------------------------------------------------
# JSON extraction from (potentially messy) LLM output
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    """Try multiple strategies to pull a JSON object from model output."""
    # Strategy 1: direct parse
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: find first { … } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Strategy 4: lenient — try fixing common issues (trailing commas)
    if brace_match:
        cleaned = re.sub(r",\s*([}\]])", r"\1", brace_match.group(0))
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from model output:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Inference backends
# ---------------------------------------------------------------------------

def _infer_api(transcript: str) -> str:
    """Call HuggingFace Inference API."""
    from huggingface_hub import InferenceClient

    if not HF_TOKEN:
        raise EnvironmentError(
            "HF_API_TOKEN is not set. "
            "Get a free token at https://huggingface.co/settings/tokens "
            "and add it to your .env file."
        )

    client = InferenceClient(model=MODEL_ID, token=HF_TOKEN)
    messages = _build_messages(transcript)

    response = client.chat_completion(
        messages=messages,
        max_tokens=MAX_NEW_TOKENS,
        temperature=0.2,          # low temp for structured output
        top_p=0.9,
    )
    return response.choices[0].message.content


def _infer_local(transcript: str) -> str:
    """Run inference on a local GPU via transformers."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

    log.info("Loading model %s locally …", MODEL_ID)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16,
        device_map="auto",
    )

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
    )

    messages = _build_messages(transcript)
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    outputs = pipe(
        prompt,
        max_new_tokens=MAX_NEW_TOKENS,
        temperature=0.2,
        top_p=0.9,
        do_sample=True,
    )

    generated = outputs[0]["generated_text"]
    # Strip the prompt from the output (model echoes it back)
    if generated.startswith(prompt):
        generated = generated[len(prompt):]
    return generated


# ---------------------------------------------------------------------------
# Public API — the ONE function app.py needs
# ---------------------------------------------------------------------------

def summarize_transcript(transcript: str) -> dict[str, Any]:
    """Summarize a meeting transcript and return the structured result dict.

    This is the drop-in replacement for ``fake_summarize`` in app.py.

    Parameters
    ----------
    transcript : str
        Raw meeting transcript text.

    Returns
    -------
    dict with keys: summary, decisions, assigned_tasks, open_questions
    """
    if not transcript or not transcript.strip():
        return {
            "summary": "No transcript provided.",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": [],
        }

    # Pick inference backend
    infer_fn = _infer_api if MODE == "api" else _infer_local

    try:
        log.info("Running inference (mode=%s, model=%s) …", MODE, MODEL_ID)
        raw_text = infer_fn(transcript)
        log.info("Raw model output (%d chars): %s", len(raw_text), raw_text[:300])

        parsed = _extract_json(raw_text)
        result = _validate_and_clean(parsed)

    except Exception as exc:
        log.error("Backend error: %s", exc, exc_info=True)
        result = {
            "summary": f"⚠️ Backend error: {exc}",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": [],
        }

    return result