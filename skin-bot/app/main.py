"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types

from app.api.routes import router
from app.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    api_key = settings.gemini_api_key.get_secret_value()
    application.state.gemini_client = (
        genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.request_timeout_seconds * 1000)
            ),
        )
        if api_key
        else None
    )
    try:
        yield
    finally:
        client = application.state.gemini_client
        if client is not None:
            await client.aio.aclose()
            client.close()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Educational skin-symptom information with image privacy and urgent-care triage safeguards.",
    version="1.0.0",
    lifespan=lifespan,
)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")