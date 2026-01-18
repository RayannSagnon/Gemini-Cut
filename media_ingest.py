from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


class IngestError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass
class UrlMetadata:
    url: str
    content_type: str
    content_length: int | None


def sanitize_url_for_logs(url: str) -> str:
    return url


def inspect_url(url: str, _allow_platform: bool) -> UrlMetadata:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise IngestError("invalid_scheme", "URL must start with http or https.")
    return UrlMetadata(url=url, content_type="video/mp4", content_length=None)


def download_url(_url: str, _output_path, _allow_platform: bool, _max_bytes: int) -> None:
    raise IngestError("platform_download_disabled", "URL download is disabled.")


def verify_video(_path) -> None:
    return None
