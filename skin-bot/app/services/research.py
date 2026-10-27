import logging
from asyncio import to_thread
from urllib.parse import urlparse

import httpx
from ddgs import DDGS
from google.genai import Client, errors, types

from app.prompts import RESEARCH_SYSTEM
from app.schemas import Source

logger = logging.getLogger(__name__)

try:
    from ddgs.http_client import HttpClient
    HttpClient._impersonates = (None,)
    HttpClient._impersonates_os = (None,)
except Exception:
    pass

ALLOWED_DOMAINS = ("dermnetnz.org", "aad.org", "mayoclinic.org", "nhs.uk", "medlineplus.gov")
TOXIC_REMEDY_TERMS = (
    "bleach",
    "apple cider vinegar",
    "garlic",
    "toothpaste",
    "kerosene",
)
FALLBACK_MODEL = "gemini-3.5-flash-lite"
RETRYABLE_STATUS_CODES = {429, 503, 504}


def _allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return parsed.scheme in {"http", "https"} and any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in ALLOWED_DOMAINS
    )


def _search_medical_sources(query: str, limit: int = 5) -> list[dict[str, str]]:
    domain_query = " OR ".join(f"site:{domain}" for domain in ALLOWED_DOMAINS)
    results: list[dict[str, str]] = []
    try:
        with DDGS() as search:
            hits = search.text(f"{query} ({domain_query})", max_results=limit)
            for hit in hits:
                url = str(hit.get("href") or hit.get("url") or "")
                title = str(hit.get("title") or "Medical information")[:300]
                body = str(hit.get("body") or hit.get("snippet") or "")[:1800]
                if _allowed_url(url) and body:
                    results.append({"title": title, "url": url, "body": body})
                if len(results) >= limit:
                    break
    except Exception:
        return []
    return results


def _contains_toxic_remedy(text: str) -> bool:
    normalized = text.casefold()
    negation_words = (
        "do not",
        "don't",
        "avoid",
        "never",
        "not recommend",
        "should not",
        "refrain",
        "harmful",
        "caustic",
        "irritat",
        "against",
        "cannot recommend",
        "warn",
        "unverified",
        "toxic",
        "danger",
    )
    for term in TOXIC_REMEDY_TERMS:
        if term not in normalized:
            continue
        sentences = [s.strip() for s in normalized.replace("\n", ". ").split(".") if term in s]
        for s in sentences:
            if not any(neg in s for neg in negation_words):
                return True
    return False


async def research_and_synthesize(
    client: Client,
    query: str,
    observations: str,
    model: str,
) -> tuple[str, list[Source]]:
    sources = await to_thread(_search_medical_sources, query)
    usable_sources = [source for source in sources if not _contains_toxic_remedy(source["body"])]
    excerpts = "\n".join(
        f"[{index}] {source['title']} ({source['url']}): {source['body']}"
        for index, source in enumerate(usable_sources, start=1)
    ) or "No verified medical sources were available. Do not invent citations."
    contents = (
        f"User question: {query}\nUncertain visual observations: {observations}\n"
        f"Verified-domain search excerpts:\n{excerpts}"
    )

    try:
        try:
            response = await _generate_response(client, model, contents)
        except (errors.APIError, httpx.TimeoutException) as exc:
            is_retryable_api_error = isinstance(exc, errors.APIError) and exc.code in RETRYABLE_STATUS_CODES
            is_timeout = isinstance(exc, httpx.TimeoutException)
            if model == FALLBACK_MODEL or not (is_retryable_api_error or is_timeout):
                raise
            logger.warning("Primary synthesis model %s failed (%s); falling back to %s", model, exc, FALLBACK_MODEL)
            response = await _generate_response(client, FALLBACK_MODEL, contents)
        answer = response.text or ""
        if not answer.strip() or _contains_toxic_remedy(answer):
            raise ValueError("Synthesis was empty or contained a blocked remedy")
    except (errors.APIError, httpx.TimeoutException, ValueError, IndexError, TypeError) as exc:
        logger.exception("Failed to obtain medical research synthesis: %s", exc)
        raise RuntimeError("Medical information synthesis is currently unavailable.") from exc

    return answer.strip(), [Source(title=source["title"], url=source["url"]) for source in usable_sources]


async def _generate_response(
    client: Client,
    model: str,
    contents: str,
) -> types.GenerateContentResponse:
    return await client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=RESEARCH_SYSTEM,
            temperature=0.2,
            max_output_tokens=2048,
        ),
    )