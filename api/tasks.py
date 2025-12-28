from celery import Celery
from faster_whisper import WhisperModel
import litellm
import os
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
app = Celery("tasks", broker=redis_url, backend=redis_url)

# Model cache
MODELS = {}

def get_model(model_size):
    if model_size not in MODELS:
        MODELS[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return MODELS[model_size]

PROMPTS = {
    "lecture": {
        "summary": "Create a summary of the lecture in 5-15 points, preserving the structure and important details.",
        "plan": "Generate a structured plan of the lecture (main sections and subsections).",
        "terms": "Identify key terms and provide a brief explanation for each.",
        "qa": "Answer user questions about the content of the lecture transcript, relying only on the text."
    },
    "meeting": {
        "summary": "Create a brief summary of the meeting (topics, decisions, key points).",
        "protocol": "Format the protocol as 'Question -> Discussion -> Decision'.",
        "tasks": "Generate a list of tasks with the responsible person, task description, deadline, and status (todo). Respond with a JSON array of objects, where each object has the keys 'assignee', 'task', 'due_date', and 'status'."
    }
}

@app.task
def transcribe_task(file_path, language, model_size):
    model = get_model(model_size)
    segments, info = model.transcribe(file_path, language=language if language != "auto" else None)

    # The result must be JSON serializable
    result_segments = []
    for segment in segments:
        result_segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        })

    return {
        "text": "".join([segment['text'] for segment in result_segments]),
        "segments": result_segments,
        "language": info.language
    }

@app.task
def post_process_task(transcript, mode, prompt_type, custom_prompt=None, provider="openai"):
    prompt = custom_prompt or PROMPTS.get(mode, {}).get(prompt_type, "")

    if not prompt:
        return {"error": "Invalid mode or prompt_type"}

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": transcript}
    ]

    # Set the model based on the provider
    model_map = {
        "openai": "gpt-4",
        "claude": "claude-2",
        "grok": "grok-1",
        "openrouter": "google/gemini-pro",
        "gemini": "gemini/gemini-pro",
        "qwen": "qwen/qwen-long",
        "perplexity": "perplexity/llama-3-sonar-large-32k-online",
    }
    # For providers like perplexity and gemini, litellm might need the provider name in the model string.
    # For others, it might infer from keys. The format 'provider/model_name' is generally safer.

    model = model_map.get(provider.lower(), "gpt-4") # Default to gpt-4

    response = litellm.completion(
        model=model,
        messages=messages
    )

    return response.choices[0].message.content
