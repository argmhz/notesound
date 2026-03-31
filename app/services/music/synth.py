from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from app.domain.schemas import MelodyModel


SAMPLE_RATE = 44100
DEFAULT_TEMPO_BPM = 120


def _midi_to_frequency(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def render_melody_to_wav(melody: MelodyModel, output_path: Path, tempo_bpm: int = DEFAULT_TEMPO_BPM) -> Path:
    if not melody.notes:
        raise ValueError("Melody contains no notes.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    seconds_per_beat = 60.0 / tempo_bpm
    playable_notes = [melody_note for melody_note in melody.notes if melody_note.pitch.midi is not None]
    if not playable_notes:
        raise ValueError("Melody contains no playable notes.")

    last_end_beat = max(
        (melody_note.start_beat if melody_note.start_beat is not None else index)
        + melody_note.duration_beats
        for index, melody_note in enumerate(playable_notes)
    )
    total_samples = max(1, int(last_end_beat * seconds_per_beat * SAMPLE_RATE))
    audio = np.zeros(total_samples, dtype=np.float32)

    for index, melody_note in enumerate(playable_notes):
        midi = melody_note.pitch.midi
        if midi is None:
            continue

        start_beat = melody_note.start_beat if melody_note.start_beat is not None else float(index)
        duration_seconds = max(0.08, melody_note.duration_beats * seconds_per_beat)
        start_sample = int(start_beat * seconds_per_beat * SAMPLE_RATE)
        sample_count = max(1, int(SAMPLE_RATE * duration_seconds))
        end_sample = min(total_samples, start_sample + sample_count)
        actual_sample_count = max(1, end_sample - start_sample)

        t = np.linspace(0, actual_sample_count / SAMPLE_RATE, actual_sample_count, endpoint=False)
        frequency = _midi_to_frequency(midi)

        # Simple monophonic synth voice with a gentle harmonic for clearer pitch.
        wave_data = (
            0.75 * np.sin(2 * math.pi * frequency * t)
            + 0.20 * np.sin(2 * math.pi * frequency * 2 * t)
            + 0.05 * np.sin(2 * math.pi * frequency * 3 * t)
        )

        fade_samples = min(int(SAMPLE_RATE * 0.01), actual_sample_count // 2)
        if fade_samples > 0:
            fade_in = np.linspace(0.0, 1.0, fade_samples)
            fade_out = np.linspace(1.0, 0.0, fade_samples)
            wave_data[:fade_samples] *= fade_in
            wave_data[-fade_samples:] *= fade_out

        audio[start_sample:end_sample] += wave_data.astype(np.float32)

    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm.tobytes())

    return output_path
