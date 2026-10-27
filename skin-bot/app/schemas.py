"""Validated API and service data models."""

from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class TriageStatus(StrEnum):
    URGENT = "urgent"
    ROUTINE = "routine"
    UNCERTAIN = "uncertain"


class VisionAssessment(BaseModel):
    triage: TriageStatus
    observations: str = Field(min_length=1, max_length=2000)
    red_flags: list[str] = Field(default_factory=list, max_length=10)
    rationale: str = Field(min_length=1, max_length=1200)


class Source(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl


class ChatResponse(BaseModel):
    answer: str
    triage: TriageStatus
    urgent: bool
    disclaimer: str
    sources: list[Source] = Field(default_factory=list)