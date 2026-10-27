"""Research model fallback tests."""

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from app.services import research


def make_client(generate_content: Any) -> Any:
    models = SimpleNamespace(generate_content=generate_content)
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def test_synthesis_falls_back_when_primary_model_is_overloaded(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    async def generate_content(*, model: str, **kwargs: Any) -> Any:
        calls.append(model)
        if len(calls) == 1:
            raise errors.APIError(
                503, {"status": "UNAVAILABLE", "message": "Model overloaded"}
            )
        return SimpleNamespace(text="Consider arranging clinician review.")

    monkeypatch.setattr(research, "_search_medical_sources", lambda query: [])

    answer, sources = asyncio.run(
        research.research_and_synthesize(
            make_client(generate_content),
            "A dry patch",
            "A small dry patch is visible.",
            "gemini-3.5-flash",
        )
    )

    assert calls == ["gemini-3.5-flash", research.FALLBACK_MODEL]
    assert answer == "Consider arranging clinician review."
    assert sources == []


def test_synthesis_does_not_fallback_for_other_provider_errors(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    async def generate_content(*, model: str, **kwargs: Any) -> Any:
        calls.append(model)
        raise errors.APIError(
            400, {"status": "INVALID_ARGUMENT", "message": "Invalid request"}
        )

    monkeypatch.setattr(research, "_search_medical_sources", lambda query: [])

    with pytest.raises(RuntimeError, match="Medical information synthesis"):
        asyncio.run(
            research.research_and_synthesize(
                make_client(generate_content),
                "A dry patch",
                "A small dry patch is visible.",
                "gemini-3.5-flash",
            )
        )

    assert calls == ["gemini-3.5-flash"]


def test_synthesis_falls_back_when_primary_request_times_out(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    async def generate_content(*, model: str, **kwargs: Any) -> Any:
        calls.append(model)
        if len(calls) == 1:
            raise httpx.ReadTimeout("request timed out")
        return SimpleNamespace(text="Consider arranging clinician review.")

    monkeypatch.setattr(research, "_search_medical_sources", lambda query: [])

    answer, _ = asyncio.run(
        research.research_and_synthesize(
            make_client(generate_content),
            "A dry patch",
            "A small dry patch is visible.",
            "gemini-3.5-flash",
        )
    )

    assert calls == ["gemini-3.5-flash", research.FALLBACK_MODEL]
    assert answer == "Consider arranging clinician review."


def test_dermnetnz_is_allowed_clinical_trusted_domain() -> None:
    assert "dermnetnz.org" in research.ALLOWED_DOMAINS
    assert research._allowed_url("https://dermnetnz.org/topics/eczema") is True
    assert research._allowed_url("https://www.dermnetnz.org/topics/psoriasis") is True
    assert research._allowed_url("https://untrusted-domain.com/cure") is False
