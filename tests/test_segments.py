from __future__ import annotations

from types import SimpleNamespace

from avatar_controller.segments import KNOWN_SEGMENTS, REQUIRED_SEGMENTS, create_empty_segment_set, validate_segments


def test_public_segment_set_contains_only_directional_playback() -> None:
    assert KNOWN_SEGMENTS == REQUIRED_SEGMENTS
    assert len(REQUIRED_SEGMENTS) == 13


def test_complete_segment_set_validates() -> None:
    metadata = SimpleNamespace(width=1280, height=720, fps=30.0, frame_count=500)
    segment_set = create_empty_segment_set("demo.mp4", metadata)
    frame = 0
    for name in REQUIRED_SEGMENTS:
        count = 15 if name.endswith("_IDLE") else 3
        segment_set.segments[name].start_frame = frame
        segment_set.segments[name].end_frame = frame + count - 1
        frame += count
    result = validate_segments(segment_set)
    assert result.errors == ()
