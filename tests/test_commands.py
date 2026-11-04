from __future__ import annotations

from pathlib import Path

import pytest

from avatar_controller.segments import REQUIRED_SEGMENTS, SegmentMark, SegmentSet, save_segments
from avatar_controller.studio.commands import StudioCommandBuilder
from avatar_controller.studio.profiles import AvatarProfile, ProfileStatus, StudioProfileError


def _profile(tmp_path: Path, status: ProfileStatus) -> AvatarProfile:
    video = tmp_path / "avatar.mp4"
    video.write_bytes(b"video")
    config = tmp_path / "profile.yaml"
    config.write_text("video:\n  path: avatar.mp4\n", encoding="utf-8")
    segments = tmp_path / "segments.yaml"
    marks: dict[str, SegmentMark] = {}
    frame = 0
    for name in REQUIRED_SEGMENTS:
        count = 15 if name.endswith("_IDLE") else 3
        marks[name] = SegmentMark(name, frame, frame + count - 1)
        frame += count
    save_segments(
        segments,
        SegmentSet(1, video, 640, 480, 30.0, 500, marks),
    )
    return AvatarProfile(
        profile_id="demo",
        name="Demo",
        status=status,
        video_path=video,
        config_path=config,
        segments_path=segments,
        report_path=tmp_path / "report.json",
        created_at="2025-01-01T00:00:00+00:00",
        width=640,
        height=480,
        fps=30.0,
        frame_count=500,
        duration_seconds=16.0,
    )


def test_virtual_camera_needs_a_reviewed_profile(tmp_path: Path) -> None:
    command_builder = StudioCommandBuilder(tmp_path, python_executable="python", frozen=False)
    with pytest.raises(StudioProfileError, match="Revisa"):
        command_builder.preview(_profile(tmp_path, ProfileStatus.REVIEW_REQUIRED), virtual_camera=True)


def test_public_preview_uses_the_generic_player(tmp_path: Path) -> None:
    command_builder = StudioCommandBuilder(tmp_path, python_executable="python", frozen=False)
    command = command_builder.preview(_profile(tmp_path, ProfileStatus.READY), virtual_camera=True)
    assert command.arguments[0].endswith("tools\\run_avatar_profile.py")
    assert "--virtual-camera" in command.arguments
