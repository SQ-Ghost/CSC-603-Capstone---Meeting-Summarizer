"""
backend.py — RecapAI Meeting-Summarizer Backend
================================================
Drop-in replacement for the stub `fake_summarize` in app.py.

Supports two inference modes (set via RECAPAI_MODE env var):
  • "api"   — HuggingFace Inference API  (default, no GPU required)
  • "local" — local transformers pipeline (requires a CUDA/MPS GPU)

Transcript chunking (ported from RecapAI.ipynb):
  Long transcripts are split at sentence boundaries into chunks of
  RECAPAI_CHUNK_SIZE characters (default 1500).  Each chunk is summarised
  independently and the results are merged with deduplication.

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
  RECAPAI_CHUNK_SIZE    max chars per transcript chunk (default: 1500)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv, set_key
from huggingface_hub import login

load_dotenv()  # reads .env in project root

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_ID: str = os.getenv("RECAPAI_MODEL", "meta-llama/Llama-3.2-1B-Instruct")
MODE: str = os.getenv("RECAPAI_MODE", "api").lower()          # "api" | "local"
HF_TOKEN: str | None = os.getenv("HF_TOKEN") or os.getenv("HF_API_TOKEN")

if not HF_TOKEN:
    print("Enter your Hugging Face token when prompted, then press Enter.")
    HF_TOKEN = input("HF Token: ").strip()
    set_key(".env", "HF_TOKEN", HF_TOKEN)
    print("Token saved to .env")

login(token=HF_TOKEN)
MAX_NEW_TOKENS: int = int(os.getenv("RECAPAI_MAX_TOKENS", "1024"))
CHUNK_SIZE: int = int(os.getenv("RECAPAI_CHUNK_SIZE", "1500"))  # max chars per chunk

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
- Do NOT duplicate tasks or decisions.
- Each assigned task must match exactly one speaker in the transcript.
- Do not infer or hallucinate extra tasks.
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
    text = text.strip()

    if not text:
        raise ValueError("Model returned empty output.")

    # Some models return the whole JSON body wrapped as a quoted string
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: remove markdown fences
    fenced = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        candidate = fenced.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text = candidate

    # Strategy 3: try wrapping if braces are missing
    candidate = text
    if not candidate.startswith("{"):
        candidate = "{" + candidate
    if not candidate.endswith("}"):
        candidate = candidate + "}"

    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Strategy 4: schema-specific salvage parser
    repaired: dict[str, Any] = {
        "summary": "",
        "decisions": [],
        "assigned_tasks": [],
        "open_questions": [],
    }

    # summary
    m = re.search(r'"summary"\s*:\s*"(.*?)"\s*,\s*"decisions"', text, re.DOTALL)
    if m:
        repaired["summary"] = m.group(1).strip()

    # decisions
    m = re.search(r'"decisions"\s*:\s*(\[[\s\S]*?\])\s*,\s*"assigned_tasks"', text, re.DOTALL)
    if m:
        try:
            repaired["decisions"] = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # assigned_tasks
    m = re.search(r'"assigned_tasks"\s*:\s*(\[[\s\S]*?\])\s*,\s*"open_questions"', text, re.DOTALL)
    if m:
        try:
            repaired["assigned_tasks"] = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # open_questions
    m = re.search(r'"open_questions"\s*:\s*(\[[\s\S]*?\])\s*$', text, re.DOTALL)
    if m:
        try:
            repaired["open_questions"] = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    if (
        repaired["summary"]
        or repaired["decisions"]
        or repaired["assigned_tasks"]
        or repaired["open_questions"]
    ):
        return repaired

    raise ValueError(f"Could not extract JSON from model output:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Inference backends
# ---------------------------------------------------------------------------

def _infer_api(transcript: str) -> str:
    """Call HuggingFace Inference API using chat completion."""
    from huggingface_hub import InferenceClient

    if not HF_TOKEN:
        raise EnvironmentError(
            "HF_API_TOKEN is not set. "
            "Get a free token at https://huggingface.co/settings/tokens "
            "and add it to your .env file."
        )

    client = InferenceClient(
        provider="novita",
        api_key=HF_TOKEN,
    )

    messages = _build_messages(transcript)

    response = client.chat_completion(
        model=MODEL_ID,
        messages=messages,
        max_tokens=MAX_NEW_TOKENS,
        temperature=0.2,
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
# Transcript chunking  (ported from RecapAI.ipynb)
# ---------------------------------------------------------------------------

def _chunk_transcript(transcript: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    """Split a transcript into smaller chunks at sentence boundaries.

    Mirrors ``chunk_transcript()`` from the notebook so that the same
    splitting behaviour is used in the backend as in Adrian's prototype.

    Parameters
    ----------
    transcript : str
        Full transcript text.
    max_chars : int
        Maximum characters per chunk (default: CHUNK_SIZE).

    Returns
    -------
    list[str]  — one or more transcript chunks.
    """
    sentences = transcript.replace("\n", " ").split(". ")
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        segment = sentence + ". "
        if len(current) + len(segment) > max_chars and current:
            chunks.append(current.strip())
            current = segment
        else:
            current += segment

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _removedupe(items: list) -> list:
    """Remove duplicates from a list while preserving order.

    Works for both plain strings and dicts (tasks) — dicts are serialised
    to a canonical JSON key for comparison, exactly as the notebook does.
    """
    seen: set[str] = set()
    result: list = []

    for item in items:
        key = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def _merge_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine per-chunk JSON outputs into one result, deduplicating lists.

    Mirrors ``merge_results()`` from the notebook.
    """
    merged: dict[str, Any] = {
        "summary":        "",
        "decisions":      [],
        "assigned_tasks": [],
        "open_questions": [],
    }

    summaries: list[str] = []
    for r in results:
        s = r.get("summary", "")
        if s:
            summaries.append(s)
        merged["decisions"]      += r.get("decisions", [])
        merged["assigned_tasks"] += r.get("assigned_tasks", [])
        merged["open_questions"] += r.get("open_questions", [])

    merged["summary"]        = " ".join(summaries)
    merged["decisions"]      = _removedupe(merged["decisions"])
    merged["assigned_tasks"] = _removedupe(merged["assigned_tasks"])
    merged["open_questions"] = _removedupe(merged["open_questions"])

    return merged


# ---------------------------------------------------------------------------
# Single-chunk summarisation (internal)
# ---------------------------------------------------------------------------

def _summarize_chunk(chunk: str) -> dict[str, Any]:
    """Send one transcript chunk through inference → JSON extraction → validation."""
    infer_fn = _infer_api if MODE == "api" else _infer_local

    raw_text = infer_fn(chunk)
    log.info("Chunk output (%d chars): %s", len(raw_text), raw_text[:300])

    parsed = _extract_json(raw_text)
    return _validate_and_clean(parsed)


# ---------------------------------------------------------------------------
# Public API — the ONE function app.py needs
# ---------------------------------------------------------------------------

def summarize_transcript(
    transcript: str,
    max_chars: int = CHUNK_SIZE,
) -> dict[str, Any]:
    """Summarize a meeting transcript and return the structured result dict.

    If the transcript exceeds *max_chars* it is split into sentence-boundary
    chunks (matching the notebook's ``summarize_meeting``), each chunk is
    summarised independently, and the results are merged with deduplication.

    This is the drop-in replacement for ``fake_summarize`` in app.py.

    Parameters
    ----------
    transcript : str
        Raw meeting transcript text.
    max_chars : int
        Maximum characters per chunk (default: CHUNK_SIZE env / 1500).

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

    try:
        log.info("Running inference (mode=%s, model=%s) …", MODE, MODEL_ID)

        # Short transcript — no chunking needed
        if len(transcript) <= max_chars:
            log.info(
                "Short transcript (%d chars ≤ %d), no chunking.",
                len(transcript), max_chars,
            )
            return _summarize_chunk(transcript)

        # Long transcript — chunk → summarise each → merge
        chunks = _chunk_transcript(transcript, max_chars)
        log.info("Split into %d chunks.", len(chunks))

        chunk_results: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            log.info(
                "--- Chunk %d of %d (%d chars) ---",
                i + 1, len(chunks), len(chunk),
            )
            chunk_results.append(_summarize_chunk(chunk))

        log.info("Merging results …")
        result = _merge_results(chunk_results)

        # Final validation pass on the merged result
        result = _validate_and_clean(result)

    except Exception as exc:
        log.error("Backend error: %s", exc, exc_info=True)
        result = {
            "summary": f"⚠️ Backend error: {exc}",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": [],
        }

    return result