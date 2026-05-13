from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.music.parser import melody_from_score, parse_musicxml


DEFAULT_SAMPLES_DIR = Path("samples/cases")


@dataclass
class CaseEvaluation:
    case_id: str
    status: str
    message: str
    expected_count: int = 0
    actual_count: int = 0
    pitch_matches: int = 0
    duration_matches: int = 0
    time_signature_expected: str | None = None
    time_signature_actual: str | None = None

    @property
    def pitch_accuracy(self) -> float:
        if self.expected_count == 0:
            return 0.0
        return self.pitch_matches / self.expected_count

    @property
    def duration_accuracy(self) -> float:
        if self.expected_count == 0:
            return 0.0
        return self.duration_matches / self.expected_count


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_musicxml(case_dir: Path) -> Path | None:
    candidates = sorted(case_dir.glob("*.musicxml")) + sorted(case_dir.glob("*.xml"))
    return candidates[0] if candidates else None


def _extract_time_signature(score) -> str | None:
    ts = score.recurse().getElementsByClass("TimeSignature").first()
    return ts.ratioString if ts is not None else None


def evaluate_case(case_dir: Path) -> CaseEvaluation:
    expected_path = case_dir / "expected.json"
    if not expected_path.exists():
        return CaseEvaluation(case_id=case_dir.name, status="skipped", message="Missing expected.json")

    expected_data = _load_json(expected_path)
    expected = expected_data.get("expected", {})
    expected_notes = expected.get("notes", [])
    expected_time_signature = expected.get("time_signature")

    musicxml_path = _find_musicxml(case_dir)
    if musicxml_path is None:
        return CaseEvaluation(
            case_id=case_dir.name,
            status="missing_output",
            message="No .musicxml or .xml output found in case folder",
            expected_count=len(expected_notes),
            time_signature_expected=expected_time_signature,
        )

    score = parse_musicxml(musicxml_path)
    melody = melody_from_score(score)
    actual_notes = melody.notes
    compare_count = min(len(expected_notes), len(actual_notes))

    pitch_matches = 0
    duration_matches = 0
    for index in range(compare_count):
        expected_note = expected_notes[index]
        actual_note = actual_notes[index]
        if expected_note.get("midi") == actual_note.pitch.midi:
            pitch_matches += 1
        expected_duration = expected_note.get("duration_beats")
        if expected_duration is not None and abs(float(expected_duration) - actual_note.duration_beats) < 0.001:
            duration_matches += 1

    return CaseEvaluation(
        case_id=case_dir.name,
        status="evaluated",
        message="ok",
        expected_count=len(expected_notes),
        actual_count=len(actual_notes),
        pitch_matches=pitch_matches,
        duration_matches=duration_matches,
        time_signature_expected=expected_time_signature,
        time_signature_actual=_extract_time_signature(score),
    )


def evaluate_samples(samples_dir: Path) -> list[CaseEvaluation]:
    case_dirs = sorted(path for path in samples_dir.iterdir() if path.is_dir())
    return [evaluate_case(case_dir) for case_dir in case_dirs]


def print_report(evaluations: list[CaseEvaluation]) -> None:
    print("Notesound sample evaluation")
    print("===========================")
    for evaluation in evaluations:
        print(f"\n{evaluation.case_id}: {evaluation.status}")
        print(f"  message: {evaluation.message}")
        print(f"  notes: expected={evaluation.expected_count} actual={evaluation.actual_count}")
        print(f"  pitch: {evaluation.pitch_matches}/{evaluation.expected_count} ({evaluation.pitch_accuracy:.0%})")
        print(f"  duration: {evaluation.duration_matches}/{evaluation.expected_count} ({evaluation.duration_accuracy:.0%})")
        print(f"  time_signature: expected={evaluation.time_signature_expected} actual={evaluation.time_signature_actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sample OMR outputs against expected melody data.")
    parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    args = parser.parse_args()

    if not args.samples_dir.exists():
        raise SystemExit(f"Samples directory does not exist: {args.samples_dir}")

    print_report(evaluate_samples(args.samples_dir))


if __name__ == "__main__":
    main()
