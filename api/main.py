from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import subprocess
import uuid
from celery.result import AsyncResult
from tasks import transcribe_task, post_process_task
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class PromptRequest(BaseModel):
    transcript: str
    mode: str
    prompt_type: str
    custom_prompt: str | None = None
    provider: str

@app.post("/transcribe/local")
async def transcribe_local(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    model: str = Form("tiny")
):
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    audio_file = file_path
    if file.content_type.startswith("video"):
        audio_file = os.path.join(UPLOAD_DIR, f"{file_id}.wav")
        subprocess.run(["ffmpeg", "-i", file_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_file])

    task = transcribe_task.delay(audio_file, language, model)
    return JSONResponse(content={"task_id": task.id})


@app.post("/prompt")
async def prompt(request: PromptRequest):
    task = post_process_task.delay(
        request.transcript,
        request.mode,
        request.prompt_type,
        request.custom_prompt,
        request.provider
    )
    return JSONResponse(content={"task_id": task.id})

@app.post("/batch/transcribe")
async def batch_transcribe(
    files: list[UploadFile] = File(...),
    language: str = Form("auto"),
    model: str = Form("tiny")
):
    task_ids = []
    for file in files:
        file_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        audio_file = file_path
        if file.content_type.startswith("video"):
            audio_file = os.path.join(UPLOAD_DIR, f"{file_id}.wav")
            subprocess.run(["ffmpeg", "-i", file_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_file])

        task = transcribe_task.delay(audio_file, language, model)
        task_ids.append(task.id)
    return JSONResponse(content={"task_ids": task_ids})


@app.get("/status/{task_id}")
async def status(task_id: str):
    task = AsyncResult(task_id)
    if task.ready():
        return JSONResponse(content={"status": task.status, "result": task.result})
    return JSONResponse(content={"status": task.status})
