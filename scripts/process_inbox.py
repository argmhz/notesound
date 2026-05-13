from __future__ import annotations

import argparse
import json
import mimetypes
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.schemas import ArtifactKind, ArtifactRef, RecognitionInput
from app.services.music.parser import build_result_payload, melody_from_score, parse_musicxml
from app.services.music.synth import (
    DEFAULT_TEMPO_BPM,
    TIMING_MODE_QUANTIZED,
    TIMING_MODE_RAW,
    render_melody_to_wav,
)
from app.services.omr.base import OmrOutput
from app.services.omr.base import OmrEngineError
from app.services.omr.factory import get_omr_engine
from app.services.preprocess.pipeline import PreprocessError, preprocess_image


DEFAULT_INBOX_DIR = Path("samples/inbox")
DEFAULT_CASES_DIR = Path("samples/cases")
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class InboxCaseResult:
    case_id: str
    status: str
    message: str


@dataclass
class OmrCandidateOutcome:
    mode: str
    input_path: Path
    omr_output: OmrOutput
    score: float
    note_count: int
    unique_duration_count: int
    dominant_duration_ratio: float
    time_signature: str | None


def slugify_case_id(name: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in name)
    collapsed = "-".join(part for part in normalized.split("-") if part)
    return collapsed or "sample"


def find_inbox_images(inbox_dir: Path) -> list[Path]:
    return sorted(path for path in inbox_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)


def reset_generated_outputs(case_dir: Path) -> None:
    for directory_name in ("preprocess", "omr"):
        directory = case_dir / directory_name
        if directory.exists():
            shutil.rmtree(directory)

    for filename in ("observed.json", "expected.draft.json"):
        path = case_dir / filename
        if path.exists():
            path.unlink()


def copy_original_image(source_path: Path, case_dir: Path) -> Path:
    destination = case_dir / f"original{source_path.suffix.lower()}"
    shutil.copy2(source_path, destination)
    return destination


def build_artifact(path: Path, kind: ArtifactKind, name: str) -> ArtifactRef:
    content_type, _ = mimetypes.guess_type(path.name)
    return ArtifactRef(
        name=name,
        kind=kind,
        path=str(path),
        content_type=content_type or "application/octet-stream",
        size_bytes=path.stat().st_size,
        url=None,
    )


def build_recognition_input(original_path: Path, preprocess_metrics) -> RecognitionInput:
    image = cv2.imread(str(original_path))
    if image is None:
        raise RuntimeError(f"Unable to decode sample image: {original_path}")

    height, width = image.shape[:2]
    content_type, _ = mimetypes.guess_type(original_path.name)
    return RecognitionInput(
        filename=original_path.name,
        content_type=content_type or "application/octet-stream",
        size_bytes=original_path.stat().st_size,
        width=width,
        height=height,
        preprocess_metrics=preprocess_metrics,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def build_expected_draft(*, case_id: str, original_filename: str, observed_payload: dict[str, Any]) -> dict[str, Any]:
    melody_notes = observed_payload.get("melody", {}).get("notes", [])
    return {
        "title": case_id,
        "image": original_filename,
        "review_required": True,
        "source": "Generated from observed.json. Review and rename to expected.json when verified.",
        "expected": {
            "time_signature": observed_payload.get("score", {}).get("time_signature"),
            "notes": [
                {
                    "midi": note.get("pitch", {}).get("midi"),
                    "duration_beats": note.get("duration_beats"),
                }
                for note in melody_notes
            ],
        },
    }


def ensure_notes_file(case_dir: Path) -> None:
    notes_path = case_dir / "notes.md"
    if notes_path.exists():
        return
    notes_path.write_text(
        "# Case Notes\n\n"
        "- Source: inbox import\n"
        "- Review the generated `expected.draft.json` and promote it to `expected.json` when verified.\n",
        encoding="utf-8",
    )


def _create_binary_input(preview_path: Path, output_path: Path) -> Path:
    preview = cv2.imread(str(preview_path), cv2.IMREAD_GRAYSCALE)
    if preview is None:
        raise RuntimeError(f"Unable to decode preprocess preview: {preview_path}")
    _, binary = cv2.threshold(preview, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), binary)
    return output_path


def _score_omr_candidate(musicxml_path: Path) -> tuple[float, int, int, float, str | None]:
    score = parse_musicxml(musicxml_path)
    melody = melody_from_score(score)
    notes = melody.notes
    if not notes:
        return -999.0, 0, 0, 1.0, None

    durations = [round(item.duration_beats, 3) for item in notes]
    unique_duration_count = len(set(durations))
    dominant_duration_ratio = max(durations.count(value) for value in set(durations)) / len(durations)
    time_signature = score.recurse().getElementsByClass("TimeSignature").first()
    ts = time_signature.ratioString if time_signature is not None else None

    midi_values = [item.pitch.midi for item in notes if item.pitch.midi is not None]
    out_of_range = sum(1 for midi in midi_values if midi < 40 or midi > 88)
    out_of_range_ratio = out_of_range / len(midi_values) if midi_values else 1.0

    heuristic_score = 0.0
    note_count = len(notes)
    if note_count >= 20:
        heuristic_score += 2.0
    elif note_count >= 8:
        heuristic_score += 1.0
    else:
        heuristic_score -= 1.5

    if unique_duration_count >= 3:
        heuristic_score += 2.5
    elif unique_duration_count == 2:
        heuristic_score += 1.0
    else:
        heuristic_score -= 2.0

    if dominant_duration_ratio < 0.72:
        heuristic_score += 2.0
    elif dominant_duration_ratio < 0.85:
        heuristic_score += 1.0
    else:
        heuristic_score -= 2.0

    if ts in {"4/4", "3/4", "2/4", "6/8", "3/8", "2/2", "12/8"}:
        heuristic_score += 1.0
    if ts in {"2/1", "4/1"}:
        heuristic_score -= 2.0

    if out_of_range_ratio > 0.35:
        heuristic_score -= 1.0

    return heuristic_score, note_count, unique_duration_count, dominant_duration_ratio, ts


def _run_candidate(mode: str, input_path: Path, case_dir: Path) -> OmrCandidateOutcome:
    omr_output = get_omr_engine().transcribe(input_path.resolve(), (case_dir / "omr" / mode).resolve())
    score, note_count, unique_duration_count, dominant_duration_ratio, time_signature = _score_omr_candidate(omr_output.musicxml_path)
    return OmrCandidateOutcome(
        mode=mode,
        input_path=input_path,
        omr_output=omr_output,
        score=score,
        note_count=note_count,
        unique_duration_count=unique_duration_count,
        dominant_duration_ratio=dominant_duration_ratio,
        time_signature=time_signature,
    )


def process_image(image_path: Path, cases_dir: Path, tempo_bpm: int) -> InboxCaseResult:
    case_id = slugify_case_id(image_path.stem)
    case_dir = cases_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    reset_generated_outputs(case_dir)

    original_path = copy_original_image(image_path, case_dir)
    ensure_notes_file(case_dir)

    try:
        preprocess_output = preprocess_image(original_path, case_dir / "preprocess")
    except PreprocessError as exc:
        return InboxCaseResult(case_id=case_id, status="failed", message=str(exc))

    binary_candidate_path = case_dir / "preprocess" / "binary_input.png"
    try:
        _create_binary_input(preprocess_output.preview_path, binary_candidate_path)
    except RuntimeError as exc:
        return InboxCaseResult(case_id=case_id, status="failed", message=str(exc))

    candidate_inputs = [
        ("original", original_path),
        ("enhanced", preprocess_output.processed_path),
        ("binary", binary_candidate_path),
    ]

    candidate_outcomes: list[OmrCandidateOutcome] = []
    candidate_errors: list[str] = []
    for mode, mode_input_path in candidate_inputs:
        try:
            candidate_outcomes.append(_run_candidate(mode, mode_input_path, case_dir))
        except OmrEngineError as exc:
            candidate_errors.append(f"{mode}:{exc.code}")

    if not candidate_outcomes:
        details = ", ".join(candidate_errors) if candidate_errors else "no candidate produced output"
        return InboxCaseResult(case_id=case_id, status="failed", message=f"omr_failed: {details}")

    best_candidate = max(candidate_outcomes, key=lambda item: item.score)
    selected_musicxml_path = (case_dir / "omr" / "result.musicxml").resolve()
    selected_musicxml_path.parent.mkdir(parents=True, exist_ok=True)
    if best_candidate.omr_output.musicxml_path.resolve() != selected_musicxml_path:
        shutil.copy2(best_candidate.omr_output.musicxml_path, selected_musicxml_path)
    omr_output = OmrOutput(
        musicxml_path=selected_musicxml_path,
        warnings=[
            *best_candidate.omr_output.warnings,
            f"omr mode selected: {best_candidate.mode}",
            "omr mode scores: "
            + ", ".join(
                f"{item.mode}={item.score:.2f}"
                for item in sorted(candidate_outcomes, key=lambda candidate: candidate.score, reverse=True)
            ),
        ],
        debug_artifacts=best_candidate.omr_output.debug_artifacts,
    )

    recognition_input = build_recognition_input(original_path, preprocess_output.metrics)
    artifacts = [
        build_artifact(original_path, ArtifactKind.original, "original"),
        build_artifact(preprocess_output.processed_path, ArtifactKind.preprocessed, "preprocessed"),
        build_artifact(preprocess_output.preview_path, ArtifactKind.preview, "preview"),
        build_artifact(binary_candidate_path, ArtifactKind.debug, "binary-input"),
        build_artifact(omr_output.musicxml_path, ArtifactKind.musicxml, "musicxml"),
    ]
    for debug_artifact in omr_output.debug_artifacts or []:
        artifacts.append(build_artifact(debug_artifact, ArtifactKind.debug, debug_artifact.name))

    observed_model = build_result_payload(
        job_id=case_id,
        status="succeeded",
        recognition_input=recognition_input,
        warnings=[*preprocess_output.warnings, *omr_output.warnings],
        confidence=max(0.4, min(0.95, 0.58 + best_candidate.score * 0.07)),
        artifacts=artifacts,
        musicxml_url=None,
        musicxml_path=omr_output.musicxml_path,
    )
    observed_payload = observed_model.model_dump(mode="json")

    write_json(case_dir / "observed.json", observed_payload)
    write_json(
        case_dir / "expected.draft.json",
        build_expected_draft(case_id=case_id, original_filename=original_path.name, observed_payload=observed_payload),
    )

    # Generate a local listening artifact so rhythm/pitch issues are easy to review.
    melody = observed_model.melody
    if melody is not None and melody.notes:
        audio_dir = case_dir / "audio"
        try:
            raw_audio_path = audio_dir / f"melody-{tempo_bpm}bpm-{TIMING_MODE_RAW}.wav"
            quantized_audio_path = audio_dir / f"melody-{tempo_bpm}bpm-{TIMING_MODE_QUANTIZED}.wav"
            render_melody_to_wav(melody, raw_audio_path, tempo_bpm=tempo_bpm, timing_mode=TIMING_MODE_RAW)
            render_melody_to_wav(melody, quantized_audio_path, tempo_bpm=tempo_bpm, timing_mode=TIMING_MODE_QUANTIZED)
            observed_payload["artifacts"].append(build_artifact(raw_audio_path, ArtifactKind.audio, "audio-raw").model_dump(mode="json"))
            observed_payload["artifacts"].append(
                build_artifact(quantized_audio_path, ArtifactKind.audio, "audio-quantized").model_dump(mode="json")
            )
            write_json(case_dir / "observed.json", observed_payload)
        except ValueError:
            # Keep case processed; audio is a convenience layer, not core OMR output.
            pass

    return InboxCaseResult(case_id=case_id, status="processed", message="ok")


def print_summary(results: list[InboxCaseResult]) -> None:
    print("Notesound inbox processing")
    print("==========================")
    for result in results:
        print(f"\n{result.case_id}: {result.status}")
        print(f"  message: {result.message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process images from samples/inbox into sample case folders.")
    parser.add_argument("--inbox-dir", type=Path, default=DEFAULT_INBOX_DIR)
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument("--tempo-bpm", type=int, default=DEFAULT_TEMPO_BPM)
    args = parser.parse_args()

    args.inbox_dir.mkdir(parents=True, exist_ok=True)
    args.cases_dir.mkdir(parents=True, exist_ok=True)

    inbox_images = find_inbox_images(args.inbox_dir)
    if not inbox_images:
        print(f"No inbox images found in {args.inbox_dir}")
        return

    results = [process_image(image_path, args.cases_dir, args.tempo_bpm) for image_path in inbox_images]
    print_summary(results)


if __name__ == "__main__":
    main()
