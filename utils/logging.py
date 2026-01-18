from __future__ import annotations

import json
from pathlib import Path


def init_job_dir(run_root: Path, job_id: str) -> Path:
    run_dir = run_root / job_id
    (run_dir / "assets").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_log(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")
