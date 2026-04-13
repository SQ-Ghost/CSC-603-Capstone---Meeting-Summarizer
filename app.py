import gradio as gr

from backend import summarize_transcript


def read_txt_file(file_obj) -> str:
    """Read uploaded .txt transcript content."""
    if file_obj is None:
        return ""

    with open(file_obj.name, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def format_markdown(result: dict) -> str:
    """Convert backend JSON into a readable markdown report."""
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
        for task in tasks:
            who = task.get("who", "Not specified")
            what = task.get("what", "").strip()
            due = task.get("due", "Not specified")
            md.append(f"- **{who}**: {what or '(no task text)'} (Due: {due})")
    else:
        md.append("- (none)")

    md.append("\n## Open Questions")
    open_questions = result.get("open_questions", []) or []
    if open_questions:
        md.append("\n".join([f"- {q}" for q in open_questions]))
    else:
        md.append("- (none)")

    return "\n".join(md)


def run_summary(transcript_text: str, transcript_file):
    """
    Generate a structured meeting summary from pasted text or uploaded file.
    Uploaded .txt content overrides the textbox when present.
    """
    if transcript_file is not None:
        transcript_text = read_txt_file(transcript_file)

    transcript_text = (transcript_text or "").strip()

    if not transcript_text:
        empty_result = {
            "summary": "No transcript provided.",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": [],
        }
        return format_markdown(empty_result), empty_result

    try:
        result = summarize_transcript(transcript_text)
        markdown_out = format_markdown(result)
        return markdown_out, result

    except Exception as exc:
        error_result = {
            "summary": "An error occurred while generating the summary.",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": [str(exc)],
        }
        return format_markdown(error_result), error_result


def clear_all():
    """Reset all UI fields."""
    return "", None, "", {}


with gr.Blocks(title="RecapAI - Meeting Summarizer") as demo:
    gr.Markdown(
        "# RecapAI\n"
        "Paste a transcript or upload a `.txt` file, then click **Generate Summary**.\n"
        "The app returns a structured summary with decisions, assigned tasks, and open questions."
    )

    with gr.Row():
        transcript_in = gr.Textbox(
            label="Transcript (paste here)",
            placeholder="Paste meeting transcript here...",
            lines=12,
        )
        transcript_upload = gr.File(
            label="Or upload a .txt transcript",
            file_types=[".txt"],
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
        outputs=[output_md, output_json],
    )

    clear_btn.click(
        fn=clear_all,
        inputs=[],
        outputs=[transcript_in, transcript_upload, output_md, output_json],
    )

demo.launch()