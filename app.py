#- Response schema expected from backend later:
#    `summary`, `decisions`, `assigned_tasks[{who,what,due}]`, `open_questions`

import gradio as gr

# ---- TEMP: Stub summarizer so UI can be built without backend/AI ----
def fake_summarize(transcript: str) -> dict:
    if not transcript or not transcript.strip():
        return {
            "summary": "No transcript provided.",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": []
        }

    return {
        "summary": "Stub summary (UI-only). Backend/AI will replace this later.",
        "decisions": [
            "Decision A (stub)",
            "Decision B (stub)"
        ],
        "assigned_tasks": [
            {"who": "Will", "what": "Build Gradio UI", "due": "TBD"}
        ],
        "open_questions": [
            "Do we standardize keys as who/what/due?"
        ]
    }

def read_txt_file(file_obj) -> str:
    if file_obj is None:
        return ""
    # Gradio provides a file object with a .name path
    with open(file_obj.name, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def format_markdown(result: dict) -> str:
    md = []

    md.append("## Summary")
    md.append(result.get("summary", "").strip() or "(none)")

    md.append("\n## Decisions")
    decisions = result.get("decisions", []) or []
    if decisions:
        md.append("\n".join([f"- {d}" for d in decisions]))
    else:
        md.append("- (none)")

    md.append("\n## Assigned Tasks")
    tasks = result.get("assigned_tasks", []) or []
    if tasks:
        for t in tasks:
            who = t.get("who", "Not specified")
            what = t.get("what", "").strip()
            due = t.get("due", "Not specified")
            md.append(f"- **{who}**: {what or '(no task text)'} (Due: {due})")
    else:
        md.append("- (none)")

    md.append("\n## Open Questions")
    oq = result.get("open_questions", []) or []
    if oq:
        md.append("\n".join([f"- {q}" for q in oq]))
    else:
        md.append("- (none)")

    return "\n".join(md)

def run_summary(transcript_text: str, transcript_file):
    # If a .txt file is uploaded, it overrides the textbox
    if transcript_file is not None:
        transcript_text = read_txt_file(transcript_file)

    result = fake_summarize(transcript_text)
    markdown_out = format_markdown(result)
    return markdown_out, result

def clear_all():
    return "", None, "", {}

with gr.Blocks(title="RecapAI - Meeting Summarizer (UI Prototype)") as demo:
    gr.Markdown(
        "# RecapAI (UI Prototype)\n"
        "Paste a transcript or upload a `.txt` file, then click **Generate Summary**.\n"
        "This version uses a **stub summarizer** so the UI can be developed before backend/AI is integrated."
    )

    with gr.Row():
        transcript_in = gr.Textbox(
            label="Transcript (paste here)",
            placeholder="Paste meeting transcript here...",
            lines=12
        )

    transcript_upload = gr.File(
        label="Or upload a .txt transcript",
        file_types=[".txt"]
    )

    with gr.Row():
        generate_btn = gr.Button("Generate Summary", variant="primary")
        clear_btn = gr.Button("Clear")

    output_md = gr.Markdown()

    with gr.Accordion("Raw JSON (debug)", open=False):
        output_json = gr.JSON()

    generate_btn.click(
        fn=run_summary,
        inputs=[transcript_in, transcript_upload],
        outputs=[output_md, output_json]
    )

    clear_btn.click(
        fn=clear_all,
        inputs=[],
        outputs=[transcript_in, transcript_upload, output_md, output_json]
    )

demo.launch()