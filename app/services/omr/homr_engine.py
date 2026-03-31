from __future__ import annotations

import subprocess
from pathlib import Path
import shutil

from app.core.config import get_settings
from app.services.omr.base import OmrEngine, OmrEngineError, OmrOutput


class HomrEngine(OmrEngine):
    def __init__(self, binary: str | None = None):
        settings = get_settings()
        self.binary = binary or settings.homr_binary

    def transcribe(self, image_path: Path, output_dir: Path) -> OmrOutput:
        if shutil.which(self.binary) is None:
            raise OmrEngineError("omr_unavailable", f"OMR binary '{self.binary}' is not available.")

        output_dir.mkdir(parents=True, exist_ok=True)
        command = [self.binary, str(image_path)]
        try:
            completed = subprocess.run(command, cwd=output_dir, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() or exc.stdout.strip() or "homr failed"
            raise OmrEngineError("omr_failed", stderr) from exc

        candidates = self._find_output_candidates(image_path=image_path, output_dir=output_dir)
        if not candidates:
            observed = self._describe_observed_files(image_path=image_path, output_dir=output_dir)
            details = completed.stderr.strip() or completed.stdout.strip() or "homr finished without reporting an error"
            raise OmrEngineError(
                "omr_failed",
                f"homr did not produce a MusicXML artifact. Details: {details}. Observed files: {observed}",
            )

        source_musicxml = candidates[0]
        canonical_musicxml = output_dir / "result.musicxml"
        if source_musicxml.resolve() != canonical_musicxml.resolve():
            shutil.copy2(source_musicxml, canonical_musicxml)
        else:
            canonical_musicxml = source_musicxml

        debug_artifacts = self._collect_debug_artifacts(image_path=image_path, output_dir=output_dir, canonical_musicxml=canonical_musicxml)
        warnings = []
        if source_musicxml.parent != output_dir:
            warnings.append("homr wrote MusicXML outside the dedicated OMR output directory; artifact was normalized.")

        return OmrOutput(musicxml_path=canonical_musicxml, warnings=warnings, debug_artifacts=debug_artifacts)

    @staticmethod
    def _find_output_candidates(*, image_path: Path, output_dir: Path) -> list[Path]:
        nearby_candidates = sorted(image_path.parent.glob(f"{image_path.stem}*.musicxml")) + sorted(
            image_path.parent.glob(f"{image_path.stem}*.xml")
        )
        output_candidates = sorted(output_dir.glob("*.musicxml")) + sorted(output_dir.glob("*.xml"))

        ordered: list[Path] = []
        for candidate in nearby_candidates + output_candidates:
            if candidate not in ordered:
                ordered.append(candidate)
        return ordered

    @staticmethod
    def _collect_debug_artifacts(*, image_path: Path, output_dir: Path, canonical_musicxml: Path) -> list[Path]:
        debug_artifacts: list[Path] = []
        nearby_patterns = [
            f"{image_path.stem}*_teaser.png",
            f"{image_path.stem}*.txt",
            f"{image_path.stem}*.json",
            f"{image_path.stem}*.log",
        ]
        for pattern in nearby_patterns:
            for candidate in sorted(image_path.parent.glob(pattern)):
                destination = output_dir / candidate.name
                if destination.resolve() != candidate.resolve():
                    shutil.copy2(candidate, destination)
                if destination != canonical_musicxml and destination not in debug_artifacts:
                    debug_artifacts.append(destination)
        return debug_artifacts

    @staticmethod
    def _describe_observed_files(*, image_path: Path, output_dir: Path) -> str:
        observed = sorted({path.name for path in image_path.parent.glob(f"{image_path.stem}*")} | {path.name for path in output_dir.glob("*")})
        return ", ".join(observed) if observed else "no related files found"
