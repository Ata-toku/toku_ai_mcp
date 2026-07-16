from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

_IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}
_BASE64_SUFFIXES = {".b64", ".base64"}
_SKIPPED_DIRECTORIES = {".git", "__pycache__", "results", "venv", ".venv"}


def _validate_runtime() -> None:
    if sys.version_info < (3, 10):
        version = ".".join(map(str, sys.version_info[:3]))
        raise RuntimeError(
            f"Python 3.10 or newer is required. Found Python {version}."
        )


def _is_image(data: bytes) -> bool:
    return data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"BM", b"II*\x00", b"MM\x00*"))


def _image_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if _is_image(data):
        return data
    try:
        decoded = base64.b64decode(b"".join(data.split()), validate=True)
    except ValueError as error:
        raise ValueError(f"Unsupported image or Base64 file: {path}") from error
    if not _is_image(decoded):
        raise ValueError(f"Base64 file does not decode to a supported image: {path}")
    return decoded


def _discover_images(directory: Path) -> list[Path]:
    candidates = []
    for candidate in directory.rglob("*"):
        if not candidate.is_file() or _SKIPPED_DIRECTORIES.intersection(candidate.parts):
            continue
        if candidate.suffix.lower() in _IMAGE_SUFFIXES | _BASE64_SUFFIXES:
            try:
                _image_bytes(candidate)
                candidates.append(candidate.resolve())
            except ValueError:
                continue
    return sorted(candidates)


def _load_request(path: Path) -> tuple[str, dict]:
    config = json.loads(path.read_text(encoding="utf-8"))
    endpoint = config.pop("EndpointUrl", "")
    image_paths = config.pop("image_paths", [])

    required_fields = (
        "FirstName",
        "LastName",
        "Sex",
        "camera",
        "DOB",
        "DiabetesStatus",
        "SmokingStatus",
    )
    missing = [field for field in required_fields if not config.get(field)]
    if missing:
        raise ValueError(f"Missing required assessment fields: {', '.join(missing)}")
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("EndpointUrl must start with http:// or https://")
    if config["Sex"] not in {"M", "F"}:
        raise ValueError("Sex must be M or F")
    if config["DiabetesStatus"] not in {"Yes", "No"}:
        raise ValueError("DiabetesStatus must be Yes or No")
    if config["SmokingStatus"] not in {"Yes", "No"}:
        raise ValueError("SmokingStatus must be Yes or No")
    if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", config["DOB"]):
        raise ValueError("DOB must match YYYY/MM/DD")
    if not isinstance(image_paths, list):
        raise ValueError("image_paths must be an array when supplied")
    if not all(isinstance(image_path, str) and image_path.strip() for image_path in image_paths):
        raise ValueError("Every image path must be a non-empty string")

    if image_paths:
        resolved_paths = [Path(value).expanduser().resolve(strict=True) for value in image_paths]
    else:
        resolved_paths = _discover_images(path.parent.resolve())
    if len(resolved_paths) < 2:
        raise ValueError(
            "At least two supported image or Base64 files are required. Place them beside "
            "assessment-request.json or supply image_paths explicitly."
        )

    config["batchimages"] = []
    for image_path in resolved_paths:
        config["batchimages"].append(
            {
                "ImageName": image_path.name,
                "Image64": base64.b64encode(_image_bytes(image_path)).decode("ascii"),
            }
        )
    return endpoint, config


def main() -> None:
    _validate_runtime()

    parser = argparse.ArgumentParser(description="Run a TokuEyes assessment locally")
    parser.add_argument("--request-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    endpoint, payload = _load_request(args.request_file)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body)
    except urllib.error.HTTPError as exc:
        result = {
            "error": str(exc),
            "statusCode": exc.code,
            "body": exc.read().decode("utf-8", errors="replace"),
        }
    except urllib.error.URLError as exc:
        result = {"error": str(exc), "statusCode": None}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    request_path = args.output_dir / f"assessment_request_{timestamp}.json"
    response_path = args.output_dir / f"assessment_response_{timestamp}.json"
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    response_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"request_path": str(request_path), "response_path": str(response_path)}))


if __name__ == "__main__":
    main()