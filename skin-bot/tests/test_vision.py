"""Vision assessment model fallback tests."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.schemas import TriageStatus
from app.services.image import SanitizedImage
from app.services.vision import (
    FALLBACK_MODEL,
    VisionServiceError,
    assess_image,
)


ASSESSMENT_JSON = (
    '{"triage":"uncertain","observations":"Image is unclear.",'
    '"red_flags":[],"rationale":"The image does not provide enough detail."}'
)


def fake_client(handler):
    models = SimpleNamespace(generate_content=handler)
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def test_vision_falls_back_when_configured_model_is_overloaded() -> None:
    calls: list[str] = []

    async def generate_content(*, model, **kwargs):
        calls.append(model)
        if len(calls) == 1:
            raise errors.APIError(
                503, {"status": "UNAVAILABLE", "message": "Model overloaded"}
            )
        return SimpleNamespace(text=ASSESSMENT_JSON)

    image = SanitizedImage(b"image", "image/jpeg", 1, 1)
    result = asyncio.run(
        assess_image(fake_client(generate_content), image, "test", "gemini-3.5-flash")
    )

    assert calls == ["gemini-3.5-flash", FALLBACK_MODEL]
    assert result.triage == TriageStatus.UNCERTAIN


def test_vision_does_not_fallback_for_nonavailability_errors() -> None:
    calls: list[str] = []

    async def generate_content(*, model, **kwargs):
        calls.append(model)
        raise errors.APIError(
            400, {"status": "INVALID_ARGUMENT", "message": "Invalid request"}
        )

    image = SanitizedImage(b"image", "image/jpeg", 1, 1)
    with pytest.raises(VisionServiceError):
        asyncio.run(
            assess_image(
                fake_client(generate_content), image, "test", "gemini-3.5-flash"
            )
        )

    assert calls == ["gemini-3.5-flash"]
