from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OmrOutput:
    musicxml_path: Path
    warnings: list[str]
    debug_artifacts: list[Path] | None = None


class OmrEngineError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class OmrEngine:
    def transcribe(self, image_path: Path, output_dir: Path) -> OmrOutput:
        raise NotImplementedError
