# Publish This Model to Replicate with Cog

This repository includes a ready-to-use Cog configuration:

- `cog.yaml`
- `predict.py`

These files expose ACE-Step 1.5 as a Replicate model with interactive UI and HTTP API.

## Prerequisites

- Docker running locally (`docker info`)
- Replicate account
- Cog CLI installed
- Optional but recommended: Hugging Face token for gated model downloads

## 1) Install Cog

```bash
sudo curl -o /usr/local/bin/cog -L https://github.com/replicate/cog/releases/latest/download/cog_`uname -s`_`uname -m`
sudo chmod +x /usr/local/bin/cog
```

## 2) Create model page on Replicate

Create a model at:

`https://replicate.com/create`

Use the exact same `<username>/<model-name>` when pushing.

## 3) Login and set tokens

```bash
cog login
export REPLICATE_API_TOKEN=r8_******
export HF_TOKEN=hf_******
```

## 4) Local test

```bash
cog predict \
  -i caption="Upbeat electronic instrumental with bright synths" \
  -i lyrics="" \
  -i duration=30 \
  -i batch_size=1
```

## 5) Push to Replicate

```bash
cog push r8.im/<your-username>/<your-model-name>
```

## 6) Run predictions from Python

```python
import replicate

output = replicate.run(
    "<your-username>/<your-model-name>:<version>",
    input={
        "caption": "Cinematic orchestral trailer music",
        "lyrics": "",
        "duration": 30,
        "batch_size": 1,
    },
)

for i, file_obj in enumerate(output):
    with open(f"output_{i}.mp3", "wb") as f:
        f.write(file_obj.read())
```

## Inputs exposed in `predict.py`

- `caption` (required)
- `lyrics`
- `duration`
- `batch_size`
- `timeout_seconds`
- `poll_interval`

## Notes

- `predict.py` starts `acestep-api` internally and talks to `/release_task` + `/query_result`.
- If checkpoints are missing, `setup()` downloads them from Hugging Face to `/src/checkpoints`.
- First startup can be slow due to model download and initialization.
