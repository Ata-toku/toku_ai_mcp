from __future__ import annotations

import base64
import json
from pathlib import Path
import socket
from urllib import error, request


ROOT = Path(r"C:\Users\AtaMoradi\Desktop\Tokueyes\Projects\toku_ai_mcp\runSpecififcTests\pas51084_pas51083")
RESULTS = ROOT / "results"
ENDPOINT = "http://100.73.176.1:8093/api/extended/analyse"


def build_case(case_name: str, first_name: str, last_name: str, sex: str, image_paths: list[Path]) -> dict:
    batchimages = []
    for image_path in image_paths:
        batchimages.append(
            {
                "ImageName": image_path.name,
                "Image64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
            }
        )

    return {
        "FirstName": first_name,
        "LastName": last_name,
        "Sex": sex,
        "camera": "NW500",
        "DOB": "1990/04/20",
        "DiabetesStatus": "No",
        "SmokingStatus": "No",
        "batchimages": batchimages,
        "_case_name": case_name,
    }


def post_case(case: dict) -> tuple[Path, Path]:
    request_file = RESULTS / f"assessment_request_{case['_case_name']}.json"
    response_file = RESULTS / f"assessment_response_{case['_case_name']}.json"

    payload = {key: value for key, value in case.items() if key != "_case_name"}
    request_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with request.urlopen(req, timeout=5) as resp:
            raw_text = resp.read().decode("utf-8", errors="replace")
        try:
            response_json = json.loads(raw_text)
        except json.JSONDecodeError:
            response_json = {"raw": raw_text}
    except error.HTTPError as exc:
        response_json = {
            "error": str(exc),
            "statusCode": exc.code,
            "body": exc.read().decode("utf-8", errors="replace"),
        }
    except (TimeoutError, socket.timeout, error.URLError) as exc:
        response_json = {"error": str(exc), "statusCode": None, "body": None}
    except Exception as exc:
        response_json = {"error": str(exc), "statusCode": None, "body": None}

    response_file.write_text(json.dumps(response_json, indent=2), encoding="utf-8")
    return request_file, response_file


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)

    cases = [
        build_case(
            "1083",
            "Case",
            "1083",
            "M",
            [
                ROOT / "pas51083" / "pas51083bs_R_03302026_091726_001.jpg",
                ROOT / "pas51083" / "pas51083bs_L_03302026_092031_001.jpg",
            ],
        ),
        build_case(
            "1084",
            "Case",
            "1084",
            "F",
            [
                ROOT / "pas51084" / "pas51084_R_03302026_092906_001.jpg",
                ROOT / "pas51084" / "pas51084_L_03302026_093044_001.jpg",
            ],
        ),
    ]

    for case in cases:
        post_case(case)

    for path in sorted(RESULTS.glob("*.json")):
        print(path.name)


if __name__ == "__main__":
    main()