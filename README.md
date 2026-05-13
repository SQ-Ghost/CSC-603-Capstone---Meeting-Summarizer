# CSC-603-Capstone---Meeting-Summarizer

A meeting summarizer powered by Llama 3.2 that generates structured JSON outputs with summaries, decisions, assigned tasks, and open questions.

## Project Structure

| File/Folder | Purpose |
|---|---|
| `notebooks/RecapAI.ipynb` | **Colab notebook** — AI-powered meeting transcript generation and summarization with interactive evaluation |
| `app.py` | **Gradio frontend** — Web UI for uploading transcripts and viewing summaries |
| `backend.py` | **Core backend** — LLM inference, JSON parsing, schema validation |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for environment variables (copy to `.env` and add your HF token) |
| `test_backend.py` | Standalone smoke-test for the backend |
| `Transcripts/` | Stores input transcripts (text files) |
| `Summaries/` | Stores generated summaries (JSON) |
| `Evaluations/` | Stores evaluation results with scores |
| `EvaluationRuns/` | Timestamped evaluation run histories |

---

## Quick Start — Local UI (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py

# Open the URL printed in the terminal (usually http://127.0.0.1:7860).
# Stop the server with Ctrl + C.
```

---

## Colab Notebook (RecapAI.ipynb)

**Link:** https://colab.research.google.com/github/SQ-Ghost/CSC-603-Capstone---Meeting-Summarizer/blob/main/notebooks/RecapAI.ipynb

### Requirements
- **Hugging Face API Token** — Required to access Llama 3.2 model
  - Get one free at https://huggingface.co/settings/tokens
  - Copy your token when prompted in the Colab notebook

### Features
- **Mock Transcript Generator** — Creates realistic office meeting transcripts
- **Transcript Summarizer** — Chunks long transcripts and generates JSON summaries
- **Automated Evaluation** — Scores summaries on clarity, faithfulness, decisions, and tasks
- **Prompt Improvement Suggestions** — Identifies issues and suggests refinements

### How to Run in Colab
1. Open the notebook link above
2. Run each cell in order
3. When prompted, paste your Hugging Face API token
4. Generate mock transcripts and evaluate them
5. Review evaluation scores and suggested improvements

# RecapAI Backend — Integration Guide

## What's included

| File | Purpose |
|---|---|
| `backend.py` | Core backend — LLM inference, JSON parsing, schema validation |
| `.env.example` | Template for environment variables |
| `requirements.txt` | Updated deps (adds `python-dotenv`, `huggingface-hub`) |
| `test_backend.py` | Standalone smoke-test (run without Gradio) |

## Quick Start

```bash
# 1. Install new deps
pip install -r requirements.txt

# 2. Create your .env
cp .env.example .env
# Edit .env → paste your HuggingFace token

# 3. Smoke-test the backend alone
python test_backend.py

# 4. Wire into app.py (see below)
```

## Wiring into app.py (2-line change)

The frontend (`app.py`) currently calls `fake_summarize()`. To swap in the
real backend, make **two small edits** at the top of `app.py`:

### Add this import (after the existing imports):
```python
from backend import summarize_transcript
```

### Replace the call inside `run_summary`:
Find this line inside `run_summary()`:
```python
result = fake_summarize(transcript_text)
```
Change it to:
```python
result = summarize_transcript(transcript_text)
```

The `fake_summarize` function and its stub data can stay in the file.

## How it works

1. **Prompt engineering** - A system prompt instructs the LLM to return
   *only* a JSON object matching the agreed schema (`summary`, `decisions`,
   `assigned_tasks[{who, what, due}]`, `open_questions`).

2. **Inference** - Two modes controlled by `RECAPAI_MODE` in `.env`:
   - `api` (default): Calls the HuggingFace Inference API. Free, no GPU
     needed, just needs a token.
   - `local`: Loads the model onto your GPU via `transformers`. Uncomment
     `torch`, `transformers`, `accelerate` in `requirements.txt` first.

3. **Robust JSON extraction** - The model doesn't always return clean JSON.
   `backend.py` tries four strategies: direct parse → strip markdown
   fences → regex for `{…}` → fix trailing commas.

4. **Schema validation** - `_validate_and_clean()` guarantees all four
   keys exist with correct types, even if the model omits something or
   returns unexpected shapes (e.g. a string instead of a list).

5. **Graceful errors** - If anything fails (network, parsing, model), the
   function returns a valid result dict with an error message in `summary`
   instead of crashing the Gradio UI.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `RECAPAI_MODE` | `api` | `api` or `local` |
| `HF_API_TOKEN` | *(none)* | Required for `api` mode |
| `RECAPAI_MODEL` | `meta-llama/Llama-3.2-1B-Instruct` | Adrian's model selection |
| `RECAPAI_MAX_TOKENS` | `1024` | Max generation length |

## Troubleshooting

**"HF_API_TOKEN is not set"**
→ Copy `.env.example` to `.env` and paste your token from
  https://huggingface.co/settings/tokens

**Model returns garbage / no JSON**
→ The extraction pipeline handles most cases, but very short transcripts
  may confuse the 1B model. Try a longer transcript, or increase
  `RECAPAI_MAX_TOKENS`.

**Rate-limited on HF API**
→ The free tier has rate limits. Wait a minute and retry, or use a
  Pro token.

**Want to use a bigger/different model?**
→ Change `RECAPAI_MODEL` in `.env`. Any HF model that supports
  chat-completion works (e.g. `mistralai/Mistral-7B-Instruct-v0.3`).