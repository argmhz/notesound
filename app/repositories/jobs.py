from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.domain.schemas import ArtifactKind, ArtifactRef, JobStatus, RecognitionJobResponse, RecognitionResultPayload
from app.repositories.models import RecognitionArtifactModel, RecognitionJobModel


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(self, *, filename: str, content_type: str, size_bytes: int, options: dict) -> RecognitionJobModel:
        job = RecognitionJobModel(
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            options=options,
            status=JobStatus.queued.value,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> RecognitionJobModel | None:
        return self.db.get(RecognitionJobModel, job_id)

    def get_artifact_by_name(self, job: RecognitionJobModel, name: str) -> RecognitionArtifactModel | None:
        return next((artifact for artifact in job.artifacts if artifact.name == name), None)

    def set_status(self, job: RecognitionJobModel, status: JobStatus) -> RecognitionJobModel:
        job.status = status.value
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def append_warning(self, job: RecognitionJobModel, warning: str) -> None:
        warnings = list(job.warnings or [])
        warnings.append(warning)
        job.warnings = warnings
        self.db.add(job)
        self.db.commit()

    def update_metrics(self, job: RecognitionJobModel, preprocess_metrics: dict | None = None, timings_ms: dict | None = None) -> None:
        if preprocess_metrics is not None:
            job.preprocess_metrics = preprocess_metrics
        if timings_ms is not None:
            job.timings_ms = timings_ms
        self.db.add(job)
        self.db.commit()

    def save_artifact(
        self,
        *,
        job: RecognitionJobModel,
        name: str,
        kind: ArtifactKind,
        path: Path,
        content_type: str,
    ) -> RecognitionArtifactModel:
        artifact = RecognitionArtifactModel(
            job_id=job.id,
            name=name,
            kind=kind.value,
            path=str(path),
            content_type=content_type,
            size_bytes=path.stat().st_size,
        )
        self.db.add(artifact)
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def save_failure(self, job: RecognitionJobModel, *, error_code: str, error_message: str) -> None:
        job.status = JobStatus.failed.value
        job.error_code = error_code
        job.error_message = error_message
        self.db.add(job)
        self.db.commit()

    def save_result(self, job: RecognitionJobModel, payload: RecognitionResultPayload) -> None:
        job.status = JobStatus.succeeded.value
        job.result_payload = payload.model_dump(mode="json")
        self.db.add(job)
        self.db.commit()

    @staticmethod
    def to_artifact_ref(artifact: RecognitionArtifactModel, url: str | None = None) -> ArtifactRef:
        return ArtifactRef(
            name=artifact.name,
            kind=artifact.kind,
            path=artifact.path,
            content_type=artifact.content_type,
            size_bytes=artifact.size_bytes,
            url=url,
        )

    def to_job_response(self, job: RecognitionJobModel, artifact_url_builder) -> RecognitionJobResponse:
        artifacts = [self.to_artifact_ref(artifact, artifact_url_builder(artifact.name)) for artifact in job.artifacts]
        return RecognitionJobResponse(
            job_id=job.id,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            warnings=job.warnings or [],
            error_code=job.error_code,
            error_message=job.error_message,
            timings_ms=job.timings_ms or {},
            artifacts=artifacts,
            result_available=job.result_payload is not None,
        )
