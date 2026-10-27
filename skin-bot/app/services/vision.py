"""Multimodal image triage using the Gemini API."""

import logging
import httpx
from google.genai import Client, errors, types

from app.prompts import VISION_SYSTEM_PROMPT
from app.schemas import TriageStatus, VisionAssessment
from app.services.image import SanitizedImage

logger = logging.getLogger(__name__)

FALLBACK_MODEL = "gemini-3.5-flash-lite"
RETRYABLE_STATUS_CODES = {429, 503, 504}


class VisionServiceError(RuntimeError):
    """Raised when a safe, structured vision assessment cannot be obtained."""


async def assess_image(
    client: Client,
    image: SanitizedImage,
    prompt: str,
    model: str,
) -> VisionAssessment:
    try:
        try:
            assessment = await _generate_assessment(client, image, prompt, model)
        except (errors.APIError, httpx.TimeoutException) as exc:
            is_retryable_api_error = isinstance(exc, errors.APIError) and exc.code in RETRYABLE_STATUS_CODES
            is_timeout = isinstance(exc, httpx.TimeoutException)
            if model == FALLBACK_MODEL or not (is_retryable_api_error or is_timeout):
                raise
            logger.warning("Primary model %s failed (%s); falling back to %s", model, exc, FALLBACK_MODEL)
            assessment = await _generate_assessment(
                client, image, prompt, FALLBACK_MODEL
            )
        if assessment.triage == TriageStatus.URGENT and not assessment.red_flags:
            assessment.red_flags.append("Potential urgent warning sign")
        return assessment
    except (errors.APIError, httpx.TimeoutException, ValueError, IndexError, TypeError) as exc:
        logger.exception("Failed to obtain vision assessment: %s", exc)
        raise VisionServiceError("Vision assessment is currently unavailable.") from exc


async def _generate_assessment(
    client: Client,
    image: SanitizedImage,
    prompt: str,
    model: str,
) -> VisionAssessment:
    response = await client.aio.models.generate_content(
        model=model,
        contents=[
            f"User context (untrusted): {prompt or 'No description provided.'}",
            types.Part.from_bytes(data=image.data, mime_type=image.media_type),
        ],
        config=types.GenerateContentConfig(
            system_instruction=VISION_SYSTEM_PROMPT,
            temperature=0,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=VisionAssessment,
        ),
    )
    if getattr(response, "parsed", None) is not None and isinstance(response.parsed, VisionAssessment):
        return response.parsed
    content = response.text
    if not content:
        raise ValueError("Vision model returned an empty result")
    return VisionAssessment.model_validate_json(content)