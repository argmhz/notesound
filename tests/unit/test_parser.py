from music21 import chord, note, stream

from app.services.music.parser import melody_from_score


def test_melody_from_score_includes_chord_notes_and_multiple_parts():
    score = stream.Score()

    part_1 = stream.Part()
    measure_1 = stream.Measure(number=1)
    measure_1.append(chord.Chord(["C4", "E4"], quarterLength=1.0))
    part_1.append(measure_1)
    score.insert(0, part_1)

    part_2 = stream.Part()
    measure_2 = stream.Measure(number=1)
    measure_2.append(note.Note("G3", quarterLength=1.0))
    part_2.append(measure_2)
    score.insert(0, part_2)

    melody = melody_from_score(score)
    notes = sorted(melody.notes, key=lambda n: (n.start_beat or 0.0, n.pitch.midi or -1))

    assert len(notes) == 3
    assert {item.pitch.midi for item in notes} == {55, 60, 64}
    assert all(item.start_beat == 0.0 for item in notes)
    assert all(item.duration_beats == 1.0 for item in notes)
    assert {item.source_staff for item in notes} == {0, 1}
