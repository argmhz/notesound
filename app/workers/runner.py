from __future__ import annotations

import logging
import mimetypes
import threading
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.schemas import ArtifactKind, JobStatus, RecognitionInput
from app.repositories.jobs import JobRepository
from app.services.music.parser import MusicParseError, build_result_payload
from app.services.omr.base import OmrEngineError
from app.services.omr.factory import get_omr_engine
from app.services.preprocess.pipeline import PreprocessError, preprocess_image


logger = logging.getLogger(__name__)


class LocalJobRunner:
    def submit(self, job_id: str) -> None:
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()

    def _run_job(self, job_id: str) -> None:
        settings = get_settings()
        db: Session = SessionLocal()
        repository = JobRepository(db)
        started = time.perf_counter()
        try:
            job = repository.get_job(job_id)
            if job is None:
                return
            repository.set_status(job, JobStatus.processing)

            job_dir = settings.artifacts_dir / job.id
            original_artifact = next((artifact for artifact in job.artifacts if artifact.name == "original"), None)
            if original_artifact is None:
                repository.save_failure(job, error_code="missing_input", error_message="Original artifact missing.")
                return

            preprocess_started = time.perf_counter()
            preprocess = preprocess_image(Path(original_artifact.path), job_dir / "preprocess")
            repository.save_artifact(
                job=job,
                name="preprocessed",
                kind=ArtifactKind.preprocessed,
                path=preprocess.processed_path,
                content_type="image/png",
            )
            repository.save_artifact(
                job=job,
                name="preview",
                kind=ArtifactKind.preview,
                path=preprocess.preview_path,
                content_type="image/png",
            )
            for warning in preprocess.warnings:
                repository.append_warning(job, warning)

            omr_started = time.perf_counter()
            omr = get_omr_engine().transcribe(preprocess.processed_path, job_dir / "omr")
            musicxml_artifact = repository.save_artifact(
                job=job,
                name="musicxml",
                kind=ArtifactKind.musicxml,
                path=omr.musicxml_path,
                content_type="application/vnd.recordare.musicxml+xml",
            )
            for warning in omr.warnings:
                repository.append_warning(job, warning)
            for debug_artifact_path in omr.debug_artifacts or []:
                repository.save_artifact(
                    job=job,
                    name=debug_artifact_path.stem,
                    kind=ArtifactKind.debug,
                    path=debug_artifact_path,
                    content_type=mimetypes.guess_type(debug_artifact_path.name)[0] or "application/octet-stream",
                )

            timings = {
                "preprocess": int((omr_started - preprocess_started) * 1000),
                "omr": int((time.perf_counter() - omr_started) * 1000),
                "total": int((time.perf_counter() - started) * 1000),
            }

            repository.update_metrics(job, preprocess_metrics=preprocess.metrics.model_dump(mode="json"), timings_ms=timings)
            job = repository.get_job(job_id)
            if job is None:
                return

            warnings = list(job.warnings or [])
            confidence = _estimate_confidence(preprocess.metrics, warnings)
            recognition_input = RecognitionInput(
                filename=job.filename,
                content_type=job.content_type,
                size_bytes=job.size_bytes,
                width=preprocess.metrics.width,
                height=preprocess.metrics.height,
                preprocess_metrics=preprocess.metrics,
            )
            artifacts = [
                repository.to_artifact_ref(
                    artifact,
                    url=f"{settings.api_prefix}/recognitions/{job.id}/artifacts/{artifact.name}",
                )
                for artifact in job.artifacts
            ]
            payload = build_result_payload(
                job_id=job.id,
                status=JobStatus.succeeded,
                recognition_input=recognition_input,
                warnings=warnings,
                confidence=confidence,
                artifacts=artifacts,
                musicxml_url=f"{settings.api_prefix}/recognitions/{job.id}/artifacts/{musicxml_artifact.name}",
                musicxml_path=omr.musicxml_path,
            )
            repository.save_result(job, payload)
        except PreprocessError as exc:
            _save_failure(repository, job_id, "preprocess_failed", str(exc))
        except OmrEngineError as exc:
            _save_failure(repository, job_id, exc.code, exc.message)
        except MusicParseError as exc:
            _save_failure(repository, job_id, "musicxml_parse_failed", str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected recognition failure for job %s", job_id)
            _save_failure(repository, job_id, "internal_error", str(exc))
        finally:
            db.close()


def _estimate_confidence(metrics, warnings: list[str]) -> float:
    confidence = 0.9
    confidence -= min(abs(metrics.skew_angle_deg) / 20.0, 0.2)
    confidence -= min(max(0.0, 30 - metrics.contrast) / 100.0, 0.2)
    confidence -= min(len(warnings) * 0.05, 0.3)
    return round(max(0.1, min(confidence, 0.99)), 2)


def _save_failure(repository: JobRepository, job_id: str, error_code: str, error_message: str) -> None:
    job = repository.get_job(job_id)
    if job is None:
        return
    repository.save_failure(job, error_code=error_code, error_message=error_message)


_runner = LocalJobRunner()


def get_job_runner() -> LocalJobRunner:
    return _runner
