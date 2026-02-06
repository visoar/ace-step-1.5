#!/usr/bin/env python3
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import runpod


API_BIND_HOST = os.environ.get("ACESTEP_API_HOST", "0.0.0.0")
API_REQUEST_HOST = os.environ.get("ACESTEP_INTERNAL_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("ACESTEP_API_PORT", "8000"))
API_BASE_URL = f"http://{API_REQUEST_HOST}:{API_PORT}"
STARTUP_TIMEOUT = int(os.environ.get("ACESTEP_API_STARTUP_TIMEOUT", "900"))
DEFAULT_DURATION = int(os.environ.get("ACESTEP_DEFAULT_DURATION", "90"))
DEFAULT_POLL_INTERVAL = int(os.environ.get("ACESTEP_POLL_INTERVAL", "3"))
DEFAULT_JOB_TIMEOUT = int(os.environ.get("ACESTEP_JOB_TIMEOUT", "1800"))

_api_process = None


def _api_request(path, data=None):
    url = f"{API_BASE_URL}{path}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ACE-Step-Runpod-Handler/1.0",
    }

    if data is not None:
        request = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )
    else:
        request = urllib.request.Request(url, headers=headers, method="GET")

    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def _download_bytes(path):
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        headers={"User-Agent": "ACE-Step-Runpod-Handler/1.0"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def _api_healthy():
    try:
        result = _api_request("/health")
        return result.get("data", {}).get("status") == "ok"
    except Exception:
        return False


def _ensure_api_running():
    global _api_process

    if _api_process is not None and _api_process.poll() is None:
        return

    os.makedirs("/app/outputs", exist_ok=True)
    stdout_file = open("/app/outputs/serverless-api.log", "a", encoding="utf-8")
    stderr_file = open("/app/outputs/serverless-api.err.log", "a", encoding="utf-8")

    _api_process = subprocess.Popen(
        ["acestep-api", "--host", API_BIND_HOST, "--port", str(API_PORT)],
        stdout=stdout_file,
        stderr=stderr_file,
    )

    started_at = time.time()
    while time.time() - started_at < STARTUP_TIMEOUT:
        if _api_process.poll() is not None:
            raise RuntimeError("acestep-api exited during startup. Check /app/outputs logs.")
        if _api_healthy():
            return
        time.sleep(2)

    raise TimeoutError(
        f"Timed out waiting for ACE-Step API health after {STARTUP_TIMEOUT} seconds"
    )


def _submit_job(caption, lyrics, duration, batch_size):
    result = _api_request(
        "/release_task",
        {
            "caption": caption,
            "lyrics": lyrics,
            "duration": duration,
            "batch_size": batch_size,
        },
    )

    if result.get("code") != 200:
        raise RuntimeError(result.get("error") or "Failed to submit task")

    task_id = result.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError("Task submitted but no task_id was returned")
    return task_id


def _poll_job(job, task_id, poll_interval, timeout_seconds):
    started_at = time.time()

    while True:
        elapsed = int(time.time() - started_at)
        if elapsed > timeout_seconds:
            raise TimeoutError(f"Generation timeout after {timeout_seconds} seconds")

        result = _api_request("/query_result", {"task_id_list": [task_id]})
        data = result.get("data") or []

        if data:
            task_result = data[0]
            status = task_result.get("status", 0)

            if status == 1:
                runpod.serverless.progress_update(job, "Generation completed")
                return task_result
            if status == 2:
                raise RuntimeError("Generation failed")

        runpod.serverless.progress_update(job, f"Generating... {elapsed}s")
        time.sleep(poll_interval)


def handler(job):
    job_input = job.get("input", {})

    caption = (job_input.get("caption") or "").strip()
    if not caption:
        return {"error": "Input 'caption' is required"}

    lyrics = job_input.get("lyrics") or ""
    duration = int(job_input.get("duration", DEFAULT_DURATION))
    batch_size = int(job_input.get("batch_size", 1))
    timeout_seconds = int(job_input.get("timeout_seconds", DEFAULT_JOB_TIMEOUT))
    poll_interval = int(job_input.get("poll_interval", DEFAULT_POLL_INTERVAL))

    include_audio_base64 = bool(job_input.get("return_audio_base64", False))
    max_base64_bytes = int(job_input.get("max_base64_bytes", 8_000_000))

    try:
        _ensure_api_running()
        task_id = _submit_job(caption, lyrics, duration, batch_size)
        runpod.serverless.progress_update(job, f"Task submitted: {task_id}")

        task_result = _poll_job(job, task_id, poll_interval, timeout_seconds)
        result_data = json.loads(task_result.get("result") or "[]")

        response = {
            "task_id": task_id,
            "status": "completed",
            "duration": duration,
            "batch_size": batch_size,
            "results": result_data,
        }

        if include_audio_base64:
            audio_items = []
            for index, item in enumerate(result_data):
                file_path = item.get("file")
                if not file_path:
                    continue

                audio_bytes = _download_bytes(file_path)
                if len(audio_bytes) > max_base64_bytes:
                    audio_items.append(
                        {
                            "index": index,
                            "file": file_path,
                            "skipped": True,
                            "reason": "file_too_large",
                            "bytes": len(audio_bytes),
                        }
                    )
                    continue

                audio_items.append(
                    {
                        "index": index,
                        "file": file_path,
                        "content_type": "audio/mpeg",
                        "base64": base64.b64encode(audio_bytes).decode("utf-8"),
                    }
                )

            response["audio"] = audio_items

        return response

    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8") if exc.fp else str(exc)
        return {"error": f"HTTP error {exc.code}: {message}"}
    except Exception as exc:
        return {"error": str(exc)}


runpod.serverless.start({"handler": handler})
