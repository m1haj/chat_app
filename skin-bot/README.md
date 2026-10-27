# skin-bot

A web-based educational skin-symptom assistant built with FastAPI, a multimodal Gemini model, and a vanilla JavaScript chat interface. It is not a diagnostic device and must not be used to delay medical care.

## Requirements

- Python 3.11 or newer
- A Gemini API key with access to the configured vision-capable model
- Internet access for the model API and DuckDuckGo search

## Run locally

```bash
cd skin-bot
python3.11 -m venv .venv311
source .venv311/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`, then start the server:

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. API documentation is at <http://127.0.0.1:8000/docs>; health status is at <http://127.0.0.1:8000/health>.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | empty | API key; without it, `/api/chat` returns HTTP 503 |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Vision-capable Gemini model |
| `MAX_UPLOAD_BYTES` | `8388608` | Maximum image upload size |
| `MAX_IMAGE_DIMENSION` | `1024` | Maximum width or height after sanitization |
| `MAX_PROMPT_CHARACTERS` | `2000` | Maximum user prompt length |
| `REQUEST_TIMEOUT_SECONDS` | `45` | Outbound model request timeout |
| `ALLOWED_ORIGINS` | empty | Optional comma-separated CORS origins; same-origin is sufficient by default |

## Tests

```bash
pytest -q
```

Tests cover supported image formats, malformed/unsupported data, resize constraints, and removal of embedded EXIF metadata.

## Docker

```bash
docker build -t skin-bot .
docker run --rm -p 8000:8000 --env-file .env skin-bot
```

## Safety and privacy

- Uploads are decoded as JPEG, PNG, or WEBP by image content, re-encoded, resized, and stripped of EXIF metadata before being sent to the model. Only the sanitized image leaves the application.
- Urgent or uncertain assessments bypass web research. The model is instructed to triage for emergency warning signs, but automated image assessment can miss serious conditions; it cannot rule out cancer, infection, or any other disease.
- Non-urgent research is constrained to DermNet, AAD, Mayo Clinic, NHS, and MedlinePlus pages. Remedy screening rejects known harmful advice; it is not a guarantee that every generated response is safe.
- Images and prompts are sent to the configured AI provider. Review that provider's data handling terms before use and do not upload identifiable or highly sensitive images.
- Before any real-world or clinical deployment, obtain clinical, privacy, security, accessibility, and regulatory review. Add authentication, rate limiting, abuse protection, monitored logging that excludes health data, and validated clinical escalation workflows for the intended jurisdiction. This sample is not production-certified medical software.

## API

`POST /api/chat` accepts `multipart/form-data` with a required `image` file and optional `prompt` text field. It returns an answer, triage status, disclaimer, and source URLs. Unsupported images return HTTP 415, oversized images HTTP 413, unconfigured model access HTTP 503, and upstream service failures HTTP 502.