"""Validate and privacy-sanitize user-provided images."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


class ImageValidationError(ValueError):
    """Raised when an upload is not a supported, decodable image."""


@dataclass(frozen=True)
class SanitizedImage:
    data: bytes
    media_type: str
    width: int
    height: int


SUPPORTED_FORMATS = {
    "JPEG": ("image/jpeg", "JPEG"),
    "PNG": ("image/png", "PNG"),
    "WEBP": ("image/webp", "WEBP"),
}
MAX_SOURCE_PIXELS = 50_000_000


def sanitize_image(data: bytes, max_dimension: int = 1024) -> SanitizedImage:
    """Decode by file signature, orient, resize, and re-encode without metadata."""
    if not data:
        raise ImageValidationError("The uploaded image is empty.")
    if max_dimension < 1:
        raise ValueError("max_dimension must be positive")

    try:
        with Image.open(BytesIO(data)) as source:
            detected = source.format
            if detected not in SUPPORTED_FORMATS:
                raise ImageValidationError("Only JPEG, PNG, and WEBP images are supported.")
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ImageValidationError("The uploaded image dimensions are too large to process safely.")
            source.verify()

        with Image.open(BytesIO(data)) as source:
            detected = source.format
            media_type, output_format = SUPPORTED_FORMATS[detected]
            image = ImageOps.exif_transpose(source)
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            if output_format == "JPEG":
                if image.mode not in ("RGB", "L"):
                    background = Image.new("RGB", image.size, "white")
                    if "A" in image.getbands():
                        background.paste(image.convert("RGBA"), mask=image.getchannel("A"))
                    else:
                        background.paste(image.convert("RGB"))
                    image = background
            elif output_format == "PNG" and image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                image = image.convert("RGBA")
            elif output_format == "WEBP" and image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")

            output = BytesIO()
            image.save(output, format=output_format, optimize=True)
            return SanitizedImage(
                data=output.getvalue(),
                media_type=media_type,
                width=image.width,
                height=image.height,
            )
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("The uploaded file is not a valid supported image.") from exc