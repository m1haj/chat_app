"""Tests that urgent and uncertain image triage cannot trigger web research."""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from typing import Any

from fastapi import UploadFile
from PIL import Image

from app.api import routes
from app.prompts import RESEARCH_SYSTEM
from app.schemas import TriageStatus, VisionAssessment
from app.services import research


def make_upload() -> UploadFile:
    image = Image.new("RGB", (16, 16), color=(30, 90, 70))
    data = BytesIO()
    image.save(data, format="JPEG")
    data.seek(0)
    return UploadFile(filename="skin.jpg", file=data)


def make_request() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(gemini_client=object())))


def assessment(triage: TriageStatus) -> VisionAssessment:
    return VisionAssessment(
        triage=triage,
        observations="A visible skin change.",
        red_flags=["Reported warning sign"] if triage == TriageStatus.URGENT else [],
        rationale="Automated triage is uncertain.",
    )


def test_urgent_triage_skips_research(monkeypatch: Any) -> None:
    async def fake_assess(*args: Any, **kwargs: Any) -> VisionAssessment:
        return assessment(TriageStatus.URGENT)

    async def unexpected_research(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Urgent assessments must not trigger research")

    monkeypatch.setattr(routes, "assess_image", fake_assess)
    monkeypatch.setattr(routes, "research_and_synthesize", unexpected_research)
    response = asyncio.run(routes.chat(make_request(), make_upload(), "It is spreading"))

    assert response.urgent is True
    assert response.triage == TriageStatus.URGENT
    assert response.sources == []


def test_uncertain_triage_skips_research(monkeypatch: Any) -> None:
    async def fake_assess(*args: Any, **kwargs: Any) -> VisionAssessment:
        return assessment(TriageStatus.UNCERTAIN)

    async def unexpected_research(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Uncertain assessments must not trigger research")

    monkeypatch.setattr(routes, "assess_image", fake_assess)
    monkeypatch.setattr(routes, "research_and_synthesize", unexpected_research)
    response = asyncio.run(routes.chat(make_request(), make_upload(), ""))

    assert response.urgent is False
    assert response.triage == TriageStatus.UNCERTAIN
    assert response.sources == []


def test_routine_triage_runs_research(monkeypatch: Any) -> None:
    async def fake_assess(*args: Any, **kwargs: Any) -> VisionAssessment:
        return assessment(TriageStatus.ROUTINE)

    async def fake_research(*args: Any, **kwargs: Any) -> tuple[str, list[Any]]:
        return "Supportive self-care information.", []

    monkeypatch.setattr(routes, "assess_image", fake_assess)
    monkeypatch.setattr(routes, "research_and_synthesize", fake_research)
    response = asyncio.run(routes.chat(make_request(), make_upload(), "A dry patch"))

    assert response.triage == TriageStatus.ROUTINE
    assert response.answer == "Supportive self-care information."


def test_research_prompt_keeps_red_flag_gate_and_weak_evidence_warning() -> None:
    text = RESEARCH_SYSTEM.lower()
    assert "red-flag" in text or "red flag" in text
    assert "evidence is weak" in text or "weak or unavailable" in text


def test_research_prompt_cites_sources_for_common_conditions(monkeypatch: Any) -> None:
    sample_conditions = ["eczema", "ringworm", "melanoma"]
    captured: list[dict[str, Any]] = []

    async def fake_generate_content(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return SimpleNamespace(text="This is based on [1].")

    class FakeModels:
        generate_content = staticmethod(fake_generate_content)

    class FakeAsyncClient:
        models = FakeModels()

    class FakeClient:
        aio = FakeAsyncClient()

    fake_sources = [
        {"title": "Eczema guidance", "url": "https://example.com/eczema", "body": "Dry itchy patches can be managed."},
        {"title": "Ringworm guidance", "url": "https://example.com/ringworm", "body": "Fungal infections usually improve with antifungal care."},
        {"title": "Melanoma guidance", "url": "https://example.com/melanoma", "body": "Any changing mole warrants evaluation."},
    ]

    def fake_search(query: str, limit: int = 5) -> list[dict[str, str]]:
        if "eczema" in query:
            return [fake_sources[0]]
        if "ringworm" in query:
            return [fake_sources[1]]
        return [fake_sources[2]]

    monkeypatch.setattr(research, "_search_medical_sources", fake_search)

    for condition in sample_conditions:
        asyncio.run(
            research.research_and_synthesize(
                FakeClient(),
                condition,
                f"The spot is a {condition} concern.",
                "gpt-4o-mini",
            )
        )

    assert captured
    assert all("[1]" in call["contents"] for call in captured)
    assert all("red-flag" in call["config"].system_instruction.lower() for call in captured)
    assert all(
        "evidence is weak" in call["config"].system_instruction.lower()
        or "weak or unavailable" in call["config"].system_instruction.lower()
        for call in captured
    )