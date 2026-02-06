# ACE-Step 1.5 Serverless API Guide

This document covers the Runpod Serverless invocation methods and handler I/O for this repository.

## Endpoint Base URL

Use your Runpod endpoint ID:

`https://api.runpod.ai/v2/<ENDPOINT_ID>/`

## Invocation Methods

### 1) Synchronous: `/runsync`

Use this when you want to block until generation completes.

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

### 2) Asynchronous: `/run` + `/status/<JOB_ID>`

Use this for long jobs and queue-friendly clients.

```bash
# Submit
curl -X POST "https://api.runpod.ai/v2/<ENDPOINT_ID>/run" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "caption": "Cinematic orchestral trailer music",
      "duration": 45
    }
  }'

# Poll status
curl -X GET "https://api.runpod.ai/v2/<ENDPOINT_ID>/status/<JOB_ID>" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>"
```

## Handler Input Schema

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `caption` | `string` | Yes | - | Music/style prompt |
| `lyrics` | `string` | No | `""` | Optional lyrics text |
| `duration` | `integer` | No | `90` | Target duration in seconds |
| `batch_size` | `integer` | No | `1` | Number of generations |
| `timeout_seconds` | `integer` | No | `1800` | Max wait for generation |
| `poll_interval` | `integer` | No | `3` | Status polling interval |
| `return_audio_base64` | `boolean` | No | `false` | Embed audio data in response |
| `max_base64_bytes` | `integer` | No | `8000000` | Skip base64 if file is larger |

## Handler Output Schema

Success payload:

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

Error payload:

```json
{
  "error": "message"
}
```

## Notes

- Internal generation uses ACE-Step REST endpoints: `/release_task`, `/query_result`, `/v1/audio`.
- If `return_audio_base64=true`, the response includes an `audio` array with base64-encoded audio entries.
