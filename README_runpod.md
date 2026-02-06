# ACE-Step 1.5 Music Generation API

Generate high-quality music from text descriptions using ACE-Step 1.5 - an open-source music generation model.

## What's Included

- **ACE-Step 1.5 models** pre-loaded (~15GB)
- **FastAPI server** with REST API endpoints
- **LLM-powered features** for lyrics/caption formatting
- **CUDA 12.8** optimized for NVIDIA GPUs

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/v1/models` | GET | List available models |
| `/release_task` | POST | Create music generation task |
| `/query_result` | POST | Query task results |
| `/format_input` | POST | Enhance lyrics/caption via LLM |
| `/v1/audio` | GET | Download generated audio |

## Quick Start

Once the pod is running:
- **Gradio UI**: `http://<POD_IP>:7860` - Web interface for music generation
- **REST API**: `http://<POD_IP>:8000` - Programmatic access

## Runpod Serverless Invocation

When published as a Runpod Serverless endpoint, use:

`https://api.runpod.ai/v2/<ENDPOINT_ID>/`

### Synchronous (`/runsync`) Example

```bash
curl -X POST "https://api.runpod.ai/v2/<ENDPOINT_ID>/runsync" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "caption": "Upbeat electronic instrumental with bright synths",
      "lyrics": "",
      "duration": 30,
      "batch_size": 1
    }
  }'
```

### Asynchronous (`/run` + `/status`) Example

```bash
# Submit job
curl -X POST "https://api.runpod.ai/v2/<ENDPOINT_ID>/run" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "caption": "Cinematic orchestral trailer music",
      "duration": 45
    }
  }'

# Check status (replace <JOB_ID>)
curl -X GET "https://api.runpod.ai/v2/<ENDPOINT_ID>/status/<JOB_ID>" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>"
```

### Expected Output (Handler)

```json
{
  "task_id": "....",
  "status": "completed",
  "duration": 30,
  "batch_size": 1,
  "results": [
    {
      "file": "/v1/audio?filename=....mp3"
    }
  ]
}
```

Optional input fields supported by this handler:
- `timeout_seconds` (default `1800`)
- `poll_interval` (default `3`)
- `return_audio_base64` (default `false`)
- `max_base64_bytes` (default `8000000`)

### CLI Tool (Recommended)

The easiest way to generate music is using the included Python CLI script. Download `generate_music.py` from the [GitHub repo](https://github.com/ValyrianTech/ace-step-1.5) and run:

```bash
python generate_music.py \
  --api-url https://<POD_ID>-8000.proxy.runpod.net \
  --caption "Upbeat indie pop with jangly guitars and energetic vocals" \
  --lyrics "[Verse 1]\nWalking down the street\nMusic in my feet\n\n[Chorus]\nWe are alive tonight" \
  --duration 90 \
  --output my_song.mp3
```

The CLI handles task submission, polling, and file download automatically. Use `--help` for all options.

### Generate Music via curl

```bash
# Create a generation task
curl -X POST http://<POD_IP>:8000/release_task \
  -H "Content-Type: application/json" \
  -d '{
    "caption": "upbeat electronic dance music with heavy bass",
    "lyrics": "[Verse]\nDancing through the night...",
    "duration": 60
  }'

# Query result (use task_id from response)
# IMPORTANT: Use task_id_list, NOT task_ids
curl -X POST http://<POD_IP>:8000/query_result \
  -H "Content-Type: application/json" \
  -d '{"task_id_list": ["<TASK_ID>"]}'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACESTEP_CONFIG_PATH` | `/app/checkpoints/acestep-v15-base` | Full path to DiT model |
| `ACESTEP_LM_MODEL_PATH` | `/app/checkpoints/acestep-5Hz-lm-1.7B` | Full path to LM model |
| `ACESTEP_API_PORT` | `8000` | API server port |

## GPU Requirements

- Minimum: 32GB VRAM
- Recommended: RTX 5090 or equivalent

## Links

- [ACE-Step GitHub](https://github.com/ace-step/ACE-Step-1.5)
- [API Documentation](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/API.md)
- [Docker Image Source](https://github.com/ValyrianTech/ace-step-1.5)
- [ValyrianTech](https://linktr.ee/ValyrianTech)
- [Patreon](http://patreon.com/ValyrianTech)
