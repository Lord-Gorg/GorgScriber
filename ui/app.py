import gradio as gr
import httpx
import os
import time
import json
import uuid
import datetime
from i18n import TRANSLATIONS
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("WHISPER_API_URL", "http://localhost:8000")
# Add a timeout to the client
client = httpx.Client(timeout=30.0)

# --- Helper Functions ---
def get_translation(lang, key):
    """Fetches a translation for a given key and language."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)

def format_timestamp(seconds, separator):
    """Formats seconds into SRT/VTT timestamp."""
    td = datetime.timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"

# --- Backend API Calls ---
def transcribe_file(file, model, language, lang_ui, progress=gr.Progress()):
    """Uploads a file to the backend and polls for transcription results."""
    if not file:
        return "Please upload a file first.", None

    progress(0, desc=get_translation(lang_ui, "uploading"))
    files = {"file": (os.path.basename(file.name), open(file.name, "rb"))}
    data = {"model": model, "language": language}

    try:
        r = client.post(f"{API_URL}/transcribe/local", files=files, data=data)
        r.raise_for_status()
        task_id = r.json()["task_id"]

        progress(0.5, desc=get_translation(lang_ui, "transcribing"))

        # Poll for results with a timeout
        for _ in range(120): # Poll for up to 10 minutes (120 * 5s)
            r = client.get(f"{API_URL}/status/{task_id}")
            r.raise_for_status()
            response = r.json()
            if response["status"] == "SUCCESS":
                return response["result"]["text"], response["result"], gr.update(visible=True), gr.update(visible=True)
            elif response["status"] == "FAILURE":
                return get_translation(lang_ui, "transcription_failed"), None, gr.update(visible=False), gr.update(visible=False)
            time.sleep(5)

        return get_translation(lang_ui, "transcription_timeout"), None, gr.update(visible=False), gr.update(visible=False)

    except httpx.RequestError as e:
        return f"API Error: {e}", None, gr.update(visible=False), gr.update(visible=False)

def process_text(transcript_data, mode, prompt_type, provider, custom_prompt, lang_ui, progress=gr.Progress()):
    """Sends transcript to the backend for post-processing and polls for results."""
    if not transcript_data:
        return "Please transcribe a file first.", "Please transcribe a file first."

    progress(0, desc=get_translation(lang_ui, "processing"))

    # Map UI mode/prompt to backend values
    mode_map = {get_translation(lang_ui, "lecture_mode"): "lecture", get_translation(lang_ui, "meeting_mode"): "meeting"}
    prompt_type_map = {
        get_translation(lang_ui, "summary"): "summary", "plan": "plan", "terms": "terms",
        "qa": "qa", "protocol": "protocol", "tasks": "tasks"
    }

    data = {
        "transcript": transcript_data["text"], "mode": mode_map.get(mode),
        "prompt_type": prompt_type_map.get(prompt_type, prompt_type),
        "provider": provider, "custom_prompt": custom_prompt
    }

    try:
        r = client.post(f"{API_URL}/prompt", json=data)
        r.raise_for_status()
        task_id = r.json()["task_id"]

        progress(0.5, desc=get_translation(lang_ui, "generating_response"))

        for _ in range(60): # Poll for up to 5 minutes (60 * 5s)
            r = client.get(f"{API_URL}/status/{task_id}")
            r.raise_for_status()
            response = r.json()
            if response["status"] == "SUCCESS":
                result_text = response["result"]
                if mode == get_translation(lang_ui, "lecture_mode"):
                    return result_text, None
                else:
                    return None, result_text
            elif response["status"] == "FAILURE":
                return get_translation(lang_ui, "processing_failed"), get_translation(lang_ui, "processing_failed")
            time.sleep(5)

        return get_translation(lang_ui, "processing_timeout"), get_translation(lang_ui, "processing_timeout")

    except httpx.RequestError as e:
        return f"API Error: {e}", f"API Error: {e}"

# --- UI Update Functions ---
def update_language(lang):
    """Updates all UI component labels based on the selected language."""
    return {
        title_md: gr.Markdown(f"# {get_translation(lang, 'title')}"),
        mode_radio: gr.Radio(label=get_translation(lang, 'mode'), choices=[get_translation(lang, "lecture_mode"), get_translation(lang, "meeting_mode")]),
        file_upload: gr.File(label=get_translation(lang, "upload_file")),
        url_input: gr.Textbox(label=get_translation(lang, "url")),
        model_dropdown: gr.Dropdown(label=get_translation(lang, "model")),
        lang_dropdown: gr.Dropdown(label=get_translation(lang, "language")),
        transcribe_button: gr.Button(get_translation(lang, "transcribe")),
        processing_dropdown: gr.Dropdown(label=get_translation(lang, "processing_type")),
        provider_dropdown: gr.Dropdown(label=get_translation(lang, "provider")),
        custom_prompt_input: gr.Textbox(label=get_translation(lang, "custom_prompt")),
        process_button: gr.Button(get_translation(lang, "process")),
        tab_raw: gr.Tab(label=get_translation(lang, "raw_transcript")),
        tab_lecture: gr.Tab(label=get_translation(lang, "lecture_result")),
        tab_meeting: gr.Tab(label=get_translation(lang, "meeting_result")),
        download_srt_button: gr.Button(get_translation(lang, "download_srt")),
        download_vtt_button: gr.Button(get_translation(lang, "download_vtt")),
        download_json_button: gr.Button(get_translation(lang, "download_json")),
    }

def update_processing_options(mode, lang):
    """Updates the processing dropdown choices based on the selected mode."""
    if mode == get_translation(lang, "lecture_mode"):
        choices = ["summary", "plan", "terms", "qa"]
    else:
        choices = ["summary", "protocol", "tasks"]
    return gr.Dropdown(choices=[get_translation(lang, c) for c in choices], value=get_translation(lang, choices[0]))

# --- File Export Functions ---
def save_srt(transcript_data):
    if not transcript_data or "segments" not in transcript_data: return None
    srt = "".join(
        f"{i+1}\n{format_timestamp(s['start'], ',')} --> {format_timestamp(s['end'], ',')}\n{s['text'].strip()}\n\n"
        for i, s in enumerate(transcript_data["segments"])
    )
    filename = f"{uuid.uuid4()}.srt"
    with open(filename, "w", encoding="utf-8") as f: f.write(srt)
    return filename

def save_vtt(transcript_data):
    if not transcript_data or "segments" not in transcript_data: return None
    vtt = "WEBVTT\n\n" + "".join(
        f"{format_timestamp(s['start'], '.')} --> {format_timestamp(s['end'], '.')}\n{s['text'].strip()}\n\n"
        for s in transcript_data["segments"]
    )
    filename = f"{uuid.uuid4()}.vtt"
    with open(filename, "w", encoding="utf-8") as f: f.write(vtt)
    return filename

def save_json_export(transcript_data, lecture_output, meeting_output):
    if not transcript_data: return None
    data = {
        "transcript": transcript_data,
        "lecture_result": lecture_output,
        "meeting_result": meeting_output,
    }
    filename = f"{uuid.uuid4()}.json"
    with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)
    return filename

# --- Gradio UI Layout ---
with gr.Blocks() as demo:
    lang_state = gr.State("en")
    transcript_data = gr.State()

    # Header
    title_md = gr.Markdown("# GorgScriber")
    lang_ui = gr.Dropdown(choices=["en", "de", "fr", "ru", "zh"], value="en", label="UI Language")

    with gr.Row():
        # Left Column: Inputs
        with gr.Column():
            mode_radio = gr.Radio(label="Mode", choices=["Lecture Mode", "Meeting Mode"], value="Lecture Mode")
            file_upload = gr.File(label="Upload Audio/Video File")
            url_input = gr.Textbox(label="URL (optional)", placeholder="Enter URL here")
            model_dropdown = gr.Dropdown(choices=["tiny", "base", "medium", "large-v3"], value="tiny", label="Model")
            lang_dropdown = gr.Dropdown(choices=["auto", "en", "ru", "de", "fr", "zh"], value="auto", label="Language")
            transcribe_button = gr.Button("Transcribe")

        # Right Column: Outputs
        with gr.Column():
            with gr.Tabs() as tabs:
                tab_raw = gr.Tab("Raw Transcript", id="raw")
                with tab_raw:
                    raw_transcript_output = gr.Textbox(lines=15, label=None)
                tab_lecture = gr.Tab("Lecture Result", id="lecture")
                with tab_lecture:
                    lecture_result_output = gr.Textbox(lines=15, label=None)
                tab_meeting = gr.Tab("Meeting Result", id="meeting")
                with tab_meeting:
                    meeting_result_output = gr.Textbox(lines=15, label=None)

    with gr.Row():
        # Post-processing controls
        with gr.Column(scale=2):
            processing_dropdown = gr.Dropdown(label="Processing Type", choices=["Summary", "Lecture Plan", "Key Terms", "Q&A"])
            provider_dropdown = gr.Dropdown(
                choices=["openai", "claude", "grok", "openrouter", "gemini", "qwen", "perplexity"],
                value="openai",
                label="Provider"
            )
            custom_prompt_input = gr.Textbox(label="Custom Prompt (optional)", placeholder="Enter custom prompt to override")
            process_button = gr.Button("Process")

        # Export buttons
        with gr.Column(scale=1):
            with gr.Row(visible=False) as export_buttons:
                download_srt_button = gr.Button("Download SRT")
                download_vtt_button = gr.Button("Download VTT")
                download_json_button = gr.Button("Download JSON")

    # --- Event Handlers ---

    # Update UI language
    lang_ui.change(
        fn=update_language,
        inputs=lang_ui,
        outputs=[
            title_md, mode_radio, file_upload, url_input, model_dropdown, lang_dropdown,
            transcribe_button, processing_dropdown, provider_dropdown, custom_prompt_input,
            process_button, tab_raw, tab_lecture, tab_meeting, download_srt_button,
            download_vtt_button, download_json_button
        ]
    ).then(
        fn=lambda lang: gr.State(lang),
        inputs=lang_ui,
        outputs=lang_state
    )

    # Update processing options when mode changes
    mode_radio.change(
        fn=update_processing_options,
        inputs=[mode_radio, lang_state],
        outputs=processing_dropdown
    )

    # Transcription button click
    transcribe_button.click(
        fn=transcribe_file,
        inputs=[file_upload, model_dropdown, lang_dropdown, lang_state],
        outputs=[raw_transcript_output, transcript_data, export_buttons]
    )

    # Processing button click
    process_button.click(
        fn=process_text,
        inputs=[transcript_data, mode_radio, processing_dropdown, provider_dropdown, custom_prompt_input, lang_state],
        outputs=[lecture_result_output, meeting_result_output]
    )

    # Export button clicks
    download_srt_button.click(fn=save_srt, inputs=transcript_data, outputs=gr.File(label="Download SRT"))
    download_vtt_button.click(fn=save_vtt, inputs=transcript_data, outputs=gr.File(label="Download VTT"))
    download_json_button.click(
        fn=save_json_export,
        inputs=[transcript_data, lecture_result_output, meeting_result_output],
        outputs=gr.File(label="Download JSON")
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
