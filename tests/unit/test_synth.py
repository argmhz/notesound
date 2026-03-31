from pathlib import Path

from app.domain.schemas import MelodyModel, MelodyNote, PitchModel
from app.services.music.synth import render_melody_to_wav


def test_render_melody_to_wav_creates_wave_file(tmp_path: Path):
    melody = MelodyModel(
        notes=[
            MelodyNote(start_beat=0.0, duration_beats=1.0, pitch=PitchModel(step="C", octave=4, midi=60)),
            MelodyNote(start_beat=2.0, duration_beats=2.0, pitch=PitchModel(step="D", octave=4, midi=62)),
        ]
    )

    output = render_melody_to_wav(melody, tmp_path / "melody.wav", tempo_bpm=120)

    assert output.exists()
    data = output.read_bytes()
    assert data[:4] == b"RIFF"
    assert len(data) > 170000
