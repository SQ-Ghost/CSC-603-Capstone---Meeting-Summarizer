import tempfile
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

    md.append("## 📌 Summary")
    md.append(result.get("summary", "").strip() or "(none)")

    md.append("\n## ✅ Decisions")
    decisions = result.get("decisions", []) or []
    if decisions:
        md.append("\n".join([f"- {d}" for d in decisions]))
    else:
        md.append("- (none)")

    md.append("\n## 🧩 Assigned Tasks")
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

def create_download_file(markdown_text: str, filename: str = "recapai_summary.txt") -> str:
    """Create a downloadable .txt file from the generated summary."""
    safe_name = filename.strip() or "recapai_summary.txt"
    if not safe_name.endswith(".txt"):
        safe_name += ".txt"

    path = f"./{safe_name}"

    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown_text)

    return path

def run_summary(transcript_text: str, transcript_file, filename: str):
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
        markdown_out = format_markdown(empty_result)
        return markdown_out, empty_result, create_download_file(markdown_out, filename)

    try:
        result = summarize_transcript(transcript_text)
        markdown_out = format_markdown(result)
        return markdown_out, result, create_download_file(markdown_out, filename)

    except Exception as exc:
        error_result = {
            "summary": "An error occurred while generating the summary.",
            "decisions": [],
            "assigned_tasks": [],
            "open_questions": [str(exc)],
        }
        markdown_out = format_markdown(error_result)
        return markdown_out, error_result, create_download_file(markdown_out, filename)


def clear_all():
    """Reset all UI fields."""
    return "", None, "recapai_summary.txt", "", {}, None


custom_css = """
:root {
    --primary-500: #7c3aed !important;
    --primary-600: #6d28d9 !important;
    --primary-700: #5b21b6 !important;
}

button.primary {
    background: #7c3aed !important;
    border-color: #7c3aed !important;
}

button.primary:hover {
    background: #6d28d9 !important;
}

.compact-upload {
    max-height: 135px !important;
    min-height: 135px !important;
    overflow: visible !important;
}

.compact-upload .wrap,
.compact-upload .container,
.compact-upload .file-preview,
.compact-upload [data-testid="file-upload"] {
    padding-top: 24px !important;
    min-height: 105px !important;
    height: 105px !important;
    padding: 8px !important;
    overflow: visible !important;
}

#transcript-box textarea {
    min-height: 430px !important;
}
"""

with gr.Blocks(
    title="RecapAI - Meeting Summarizer",
    theme=gr.themes.Soft(primary_hue="purple"),
    css=custom_css,
) as demo:
    gr.Markdown(
        """
        # 🧠 RecapAI

        Turn meeting transcripts into a structured summary with decisions,
        assigned tasks, and open questions.

        Paste a transcript or upload a `.txt` file, then click **Generate Summary**.
        """
    )

    with gr.Column():
        transcript_in = gr.Textbox(
            label="Transcript (paste here)",
            placeholder="Paste meeting transcript here...",
            lines=18,
            elem_id="transcript-box",
        )

        transcript_upload = gr.File(
            label="Upload a .txt transcript",
            file_types=[".txt"],
            elem_classes=["compact-upload"],
        )

    with gr.Row():
        generate_btn = gr.Button("Generate Summary", variant="primary")
        clear_btn = gr.Button("Clear")

    output_md = gr.Markdown()

    download_file = gr.File(label=" ⬇️ Download Summary as .txt")

    with gr.Accordion("Raw JSON (debug)", open=False):
        output_json = gr.JSON()

    filename_in = gr.Textbox(
        label="Output filename",
        value="recapai_summary.txt",
        placeholder="recapai_summary.txt",
    )
    
    generate_btn.click(
        fn=run_summary,
        inputs=[transcript_in, transcript_upload, filename_in],
        outputs=[output_md, output_json, download_file],
        show_progress=True,
    )

    clear_btn.click(
        fn=clear_all,
        inputs=[],
        outputs=[transcript_in, transcript_upload, filename_in, output_md, output_json, download_file],
    )

demo.launch()