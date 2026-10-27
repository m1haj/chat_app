"""Chat endpoint with upload validation and triage-gated research."""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from google.genai.errors import APIError

from app.config import get_settings
from app.prompts import DISCLAIMER, UNCERTAIN_RESPONSE, URGENT_RESPONSE
from app.schemas import ChatResponse, TriageStatus
from app.services.image import ImageValidationError, sanitize_image
from app.services.research import research_and_synthesize
from app.services.vision import VisionServiceError, assess_image

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    image: Annotated[UploadFile, File(description="JPEG, PNG, or WEBP image")],
    prompt: Annotated[str, Form(max_length=10000)] = "",
) -> ChatResponse:
    settings = get_settings()
    client = request.app.state.gemini_client
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not configured. Set GEMINI_API_KEY and restart the app.",
        )

    prompt = prompt.strip()
    if len(prompt) > settings.max_prompt_characters:
        raise HTTPException(status_code=422, detail="The text prompt is too long.")

    try:
        raw_image = await image.read(settings.max_upload_bytes + 1)
        if len(raw_image) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Image exceeds the upload size limit.")
        sanitized = sanitize_image(raw_image, settings.max_image_dimension)
    except ImageValidationError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    finally:
        await image.close()

    try:
        assessment = await assess_image(client, sanitized, prompt, settings.gemini_model)
    except (VisionServiceError, APIError) as exc:
        logger.error("Vision assessment error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if assessment.triage == TriageStatus.URGENT:
        return ChatResponse(
            answer=URGENT_RESPONSE,
            triage=assessment.triage,
            urgent=True,
            disclaimer=DISCLAIMER,
        )
    if assessment.triage == TriageStatus.UNCERTAIN:
        return ChatResponse(
            answer=UNCERTAIN_RESPONSE,
            triage=assessment.triage,
            urgent=False,
            disclaimer=DISCLAIMER,
        )

    try:
        answer, sources = await research_and_synthesize(
            client,
            prompt or "supportive skin symptom care",
            assessment.observations,
            settings.gemini_model,
        )
    except (RuntimeError, APIError) as exc:
        logger.error("Research synthesis error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        answer=answer,
        triage=assessment.triage,
        urgent=False,
        disclaimer=DISCLAIMER,
        sources=sources,
    )