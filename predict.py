import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path as LocalPath

from cog import BasePredictor, Input, Path
from huggingface_hub import snapshot_download


CHECKPOINTS_DIR = LocalPath(os.environ.get("CHECKPOINTS_DIR", "/src/checkpoints"))
DOWNLOAD_RETRIES = int(os.environ.get("ACESTEP_DOWNLOAD_RETRIES", "3"))
DOWNLOAD_RETRY_WAIT = int(os.environ.get("ACESTEP_DOWNLOAD_RETRY_WAIT", "10"))
STARTUP_TIMEOUT = int(os.environ.get("ACESTEP_API_STARTUP_TIMEOUT", "900"))


class Predictor(BasePredictor):
    def setup(self) -> None:
        self._api_process: subprocess.Popen | None = None
        self._stdout_file = None
        self._stderr_file = None

        self._ensure_models_present()
        self._configure_environment()
        self._ensure_api_running()

    def predict(
        self,
        caption: str = Input(description="Music style prompt, e.g. genre/instruments/mood"),
        lyrics: str = Input(
            description="Optional lyrics with tags like [Verse] and [Chorus]",
            default="",
        ),
        duration: int = Input(
            description="Target duration in seconds",
            default=90,
            ge=1,
            le=600,
        ),
        batch_size: int = Input(
            description="Number of variations to generate",
            default=1,
            ge=1,
            le=4,
        ),
        timeout_seconds: int = Input(
            description="Timeout for the generation task",
            default=1800,
            ge=30,
            le=7200,
        ),
        poll_interval: float = Input(
            description="Seconds between polling attempts",
            default=3.0,
            ge=1.0,
            le=30.0,
        ),
    ) -> list[Path]:
        self._ensure_api_running()

        task_id = self._submit_job(
            caption=caption.strip(),
            lyrics=lyrics,
            duration=duration,
            batch_size=batch_size,
        )
        task_result = self._poll_job(
            task_id=task_id,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )

        result_items = self._parse_result_items(task_result)
        outputs: list[Path] = []

        for index, item in enumerate(result_items):
            file_path = item.get("file")
            if not file_path:
                continue

            audio_bytes = self._download_bytes(file_path)
            suffix = _guess_suffix(file_path)
            output_path = LocalPath(f"/tmp/{task_id}_{index}{suffix}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_bytes)
            outputs.append(Path(str(output_path)))

        if not outputs:
            raise RuntimeError("Generation finished but no audio files were returned.")

        return outputs

    def _configure_environment(self) -> None:
        output_dir = LocalPath(os.environ.get("ACESTEP_OUTPUT_DIR", "/tmp/acestep-outputs"))
        output_dir.mkdir(parents=True, exist_ok=True)

        os.environ.setdefault("ACESTEP_PROJECT_ROOT", "/src")
        os.environ.setdefault("ACESTEP_OUTPUT_DIR", str(output_dir))
        os.environ.setdefault("ACESTEP_TMPDIR", str(output_dir))
        os.environ.setdefault("ACESTEP_DEVICE", "cuda")
        os.environ.setdefault("ACESTEP_LM_BACKEND", "pt")
        os.environ.setdefault("ACESTEP_API_HOST", "0.0.0.0")
        os.environ.setdefault("ACESTEP_API_PORT", "8000")
        os.environ.setdefault("ACESTEP_CONFIG_PATH", str(CHECKPOINTS_DIR / "acestep-v15-base"))
        os.environ.setdefault(
            "ACESTEP_LM_MODEL_PATH",
            str(CHECKPOINTS_DIR / "acestep-5Hz-lm-1.7B"),
        )

        self._api_bind_host = os.environ["ACESTEP_API_HOST"]
        self._api_request_host = os.environ.get("ACESTEP_INTERNAL_API_HOST", "127.0.0.1")
        self._api_port = int(os.environ["ACESTEP_API_PORT"])
        self._api_base_url = f"http://{self._api_request_host}:{self._api_port}"
        self._log_dir = output_dir

    def _ensure_models_present(self) -> None:
        lm_path = CHECKPOINTS_DIR / "acestep-5Hz-lm-1.7B"
        base_path = CHECKPOINTS_DIR / "acestep-v15-base"

        if lm_path.exists() and base_path.exists():
            return

        token = (os.environ.get("HF_TOKEN") or "").strip() or None
        CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)

        downloads = [
            ("ACE-Step/Ace-Step1.5", CHECKPOINTS_DIR, ["acestep-v15-turbo/*"]),
            ("ACE-Step/acestep-v15-base", CHECKPOINTS_DIR / "acestep-v15-base", None),
        ]

        for repo_id, local_dir, ignore_patterns in downloads:
            self._download_snapshot_with_retry(
                repo_id=repo_id,
                local_dir=local_dir,
                token=token,
                ignore_patterns=ignore_patterns,
            )

        # Some ACE-Step startup checks expect this directory to exist.
        (CHECKPOINTS_DIR / "acestep-v15-turbo").mkdir(parents=True, exist_ok=True)

    def _download_snapshot_with_retry(
        self,
        repo_id: str,
        local_dir: LocalPath,
        token: str | None,
        ignore_patterns: list[str] | None,
    ) -> None:
        last_error: Exception | None = None

        for attempt in range(1, DOWNLOAD_RETRIES + 1):
            try:
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=str(local_dir),
                    token=token,
                    ignore_patterns=ignore_patterns,
                )
                return
            except Exception as error:  # pragma: no cover - depends on HF network
                last_error = error
                if attempt < DOWNLOAD_RETRIES:
                    time.sleep(DOWNLOAD_RETRY_WAIT)

        if last_error is not None:
            raise RuntimeError(f"Failed to download model {repo_id}: {last_error}") from last_error

    def _ensure_api_running(self) -> None:
        if self._api_process is not None and self._api_process.poll() is None:
            return

        self._stdout_file = open(self._log_dir / "acestep-api.log", "a", encoding="utf-8")
        self._stderr_file = open(self._log_dir / "acestep-api.err.log", "a", encoding="utf-8")

        self._api_process = subprocess.Popen(
            ["acestep-api", "--host", self._api_bind_host, "--port", str(self._api_port)],
            stdout=self._stdout_file,
            stderr=self._stderr_file,
            env=os.environ.copy(),
        )

        started_at = time.time()
        while time.time() - started_at < STARTUP_TIMEOUT:
            if self._api_process.poll() is not None:
                raise RuntimeError(
                    "acestep-api exited during startup. Check logs in ACESTEP_OUTPUT_DIR."
                )
            if self._api_healthy():
                return
            time.sleep(2)

        raise TimeoutError(f"Timed out waiting for ACE-Step API ({STARTUP_TIMEOUT}s)")

    def _api_healthy(self) -> bool:
        try:
            result = self._api_request("/health")
            return result.get("data", {}).get("status") == "ok"
        except Exception:
            return False

    def _api_request(self, path: str, data: dict | None = None) -> dict:
        url = f"{self._api_base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ACE-Step-Cog/1.0",
        }

        if data is None:
            request = urllib.request.Request(url, headers=headers, method="GET")
        else:
            request = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST",
            )

        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else {}

    def _submit_job(self, caption: str, lyrics: str, duration: int, batch_size: int) -> str:
        if not caption:
            raise ValueError("Input 'caption' is required.")

        result = self._api_request(
            "/release_task",
            {
                "caption": caption,
                "lyrics": lyrics,
                "duration": duration,
                "batch_size": batch_size,
            },
        )

        if result.get("code") != 200:
            raise RuntimeError(result.get("error") or "Failed to submit generation task.")

        task_id = result.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError("Task submitted but no task_id was returned.")
        return task_id

    def _poll_job(self, task_id: str, poll_interval: float, timeout_seconds: int) -> dict:
        started_at = time.time()

        while True:
            elapsed = time.time() - started_at
            if elapsed > timeout_seconds:
                raise TimeoutError(f"Generation timed out after {timeout_seconds} seconds.")

            result = self._api_request("/query_result", {"task_id_list": [task_id]})
            data = result.get("data") or []
            if data:
                task_result = data[0]
                status = task_result.get("status", 0)
                if status == 1:
                    return task_result
                if status == 2:
                    raise RuntimeError("Generation failed.")

            time.sleep(poll_interval)

    def _parse_result_items(self, task_result: dict) -> list[dict]:
        raw_result = task_result.get("result")
        if isinstance(raw_result, list):
            return raw_result
        if isinstance(raw_result, str):
            parsed = json.loads(raw_result or "[]")
            if isinstance(parsed, list):
                return parsed
        raise RuntimeError("Unexpected generation result payload.")

    def _download_bytes(self, path_or_url: str) -> bytes:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = f"{self._api_base_url}{path_or_url}"

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ACE-Step-Cog/1.0"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.read()


def _guess_suffix(file_reference: str) -> str:
    parsed = urllib.parse.urlparse(file_reference)
    query = urllib.parse.parse_qs(parsed.query)
    candidate = ""

    if query.get("path"):
        candidate = urllib.parse.unquote(query["path"][0])
    elif query.get("filename"):
        candidate = urllib.parse.unquote(query["filename"][0])
    elif parsed.path:
        candidate = urllib.parse.unquote(parsed.path)

    suffix = LocalPath(candidate).suffix
    return suffix or ".mp3"
