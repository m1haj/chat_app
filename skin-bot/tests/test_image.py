"""Tests for image format validation and metadata sanitization."""

from io import BytesIO

import pytest
from PIL import Image

from app.services import image as image_service
from app.services.image import ImageValidationError, sanitize_image


def make_image_bytes(
    image_format: str = "JPEG",
    size: tuple[int, int] = (1800, 900),
    with_exif: bool = False,
) -> bytes:
    image = Image.new("RGB", size, color=(35, 120, 80))
    output = BytesIO()
    options: dict[str, object] = {}
    if with_exif:
        exif = Image.Exif()
        exif[270] = "private camera description"
        exif[315] = "private artist name"
        options["exif"] = exif
    image.save(output, format=image_format, **options)
    return output.getvalue()


def test_sanitize_strips_exif_metadata() -> None:
    sanitized = sanitize_image(make_image_bytes(with_exif=True))

    with Image.open(BytesIO(sanitized.data)) as output:
        assert output.getexif() == {}
    assert b"private camera description" not in sanitized.data
    assert b"private artist name" not in sanitized.data


def test_sanitize_resizes_while_preserving_aspect_ratio() -> None:
    sanitized = sanitize_image(make_image_bytes(size=(2400, 1200)), max_dimension=1024)

    assert (sanitized.width, sanitized.height) == (1024, 512)
    assert sanitized.media_type == "image/jpeg"
    with Image.open(BytesIO(sanitized.data)) as output:
        assert output.size == (1024, 512)


@pytest.mark.parametrize(
    ("image_format", "expected_media_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_supported_formats_are_detected_from_image_data(
    image_format: str,
    expected_media_type: str,
) -> None:
    sanitized = sanitize_image(make_image_bytes(image_format, size=(64, 48)))

    assert sanitized.media_type == expected_media_type
    with Image.open(BytesIO(sanitized.data)) as output:
        assert output.format == image_format


@pytest.mark.parametrize("data", [b"", b"not an image", b"<svg xmlns='http://www.w3.org/2000/svg'/>"])
def test_rejects_invalid_or_unsupported_data(data: bytes) -> None:
    with pytest.raises(ImageValidationError):
        sanitize_image(data)


def test_rejects_image_larger_than_supported_formats() -> None:
    bmp = make_image_bytes("BMP", size=(20, 20))

    with pytest.raises(ImageValidationError, match="Only JPEG, PNG, and WEBP"):
        sanitize_image(bmp)


def test_rejects_excessive_source_pixel_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_service, "MAX_SOURCE_PIXELS", 100)

    with pytest.raises(ImageValidationError, match="dimensions are too large"):
        sanitize_image(make_image_bytes(size=(16, 16)))