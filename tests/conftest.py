from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.omr.base import OmrOutput
from app.workers import runner as runner_module


FIXTURE_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>Music</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
      </note>
      <note>
        <rest/>
        <duration>1</duration>
        <type>quarter</type>
      </note>
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>2</duration>
        <type>half</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


class ImmediateRunner:
    def __init__(self, worker):
        self.worker = worker

    def submit(self, job_id: str) -> None:
        self.worker._run_job(job_id)


class FakeOmrEngine:
    def transcribe(self, image_path: Path, output_dir: Path) -> OmrOutput:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "result.musicxml"
        path.write_text(FIXTURE_MUSICXML, encoding="utf-8")
        return OmrOutput(musicxml_path=path, warnings=[], debug_artifacts=[])


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTESOUND_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("NOTESOUND_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    from app.core.config import get_settings
    from app.core import db as db_module
    from app.main import create_app

    get_settings.cache_clear()
    db_module.settings = get_settings()
    db_module.engine.dispose()
    db_module.engine = db_module.create_engine(
        db_module.settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
    db_module.SessionLocal.configure(bind=db_module.engine)
    monkeypatch.setattr(runner_module, "get_omr_engine", lambda: FakeOmrEngine())
    monkeypatch.setattr("app.api.routes.get_job_runner", lambda: ImmediateRunner(runner_module.LocalJobRunner()))
    create_app()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    from app.main import create_app

    app = create_app()
    return TestClient(app)
