from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from avatar_controller.segments import SegmentMark, SegmentSet, TEMPORAL_SEGMENT_ORDER
from avatar_controller.studio.companion import reviewed_profile_arguments
from avatar_controller.studio.profiles import AvatarProfileStore, ProfileStatus, StudioProfileError
from avatar_controller.video_io import VideoMetadata


@pytest.fixture
def reviewed_profile(tmp_path: Path):
    workspace = tmp_path / "workspace"
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"synthetic; not played")
    store = AvatarProfileStore(workspace / "data" / "studio")
    profile = store.create_imported_profile(video, VideoMetadata(video, 320, 240, 30, 500, 500/30))
    marks = {
        name: SegmentMark(name, i * 30, i * 30 + (19 if name.endswith("_IDLE") else 4))
        for i, name in enumerate(TEMPORAL_SEGMENT_ORDER)
    }
    segments = SegmentSet(1, video, 320, 240, 30, 500, marks)
    profile.segments_path.write_text(yaml.safe_dump(segments.to_yaml_data()), encoding="utf-8")
    profile = store.update_status(profile.profile_id, ProfileStatus.READY)
    return workspace, store, profile


def test_reviewed_profile_produces_the_bundled_public_output_command(reviewed_profile) -> None:
    workspace, _store, profile = reviewed_profile
    args = reviewed_profile_arguments(workspace, profile.profile_id)
    assert args[:2] == ("--internal-tool", "run_avatar_profile.py")
    assert "--virtual-camera" in args
    assert "--no-overlay" in args
    assert str(profile.config_path) in args


def test_automatic_output_rejects_unreviewed_and_missing_profiles(reviewed_profile) -> None:
    workspace, store, profile = reviewed_profile
    store.update_status(profile.profile_id, ProfileStatus.REVIEW_REQUIRED)
    with pytest.raises(StudioProfileError, match="revisado"):
        reviewed_profile_arguments(workspace, profile.profile_id)
    with pytest.raises(StudioProfileError, match="does not exist"):
        reviewed_profile_arguments(workspace, "missing")


def test_profile_check_and_list_do_not_start_playback(reviewed_profile, capsys, monkeypatch) -> None:
    workspace, _store, profile = reviewed_profile
    entry = Path(__file__).resolve().parents[1] / "tools" / "run_avatar_studio.py"
    spec = importlib.util.spec_from_file_location("studio_entry", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def unexpected(*args, **kwargs):
        pytest.fail("validation must not start playback")
    monkeypatch.setattr(module, "run_internal_tool", unexpected)
    assert module.main(["--workspace", str(workspace), "--list-profiles"]) == 0
    assert profile.profile_id in capsys.readouterr().out
    assert module.main([
        "--workspace", str(workspace), "--play-profile", profile.profile_id, "--check-profile"
    ]) == 0
    assert "no camera" in capsys.readouterr().out


def test_public_play_command_dispatches_to_the_same_profile_tool(reviewed_profile, monkeypatch) -> None:
    workspace, _store, profile = reviewed_profile
    entry = Path(__file__).resolve().parents[1] / "tools" / "run_avatar_studio.py"
    spec = importlib.util.spec_from_file_location("studio_play_entry", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = {}
    def capture(tool, arguments, *, project_root):
        captured.update(tool=tool, arguments=arguments, project_root=project_root)
        return 0
    monkeypatch.setattr(module, "run_internal_tool", capture)
    assert module.main([
        "--workspace", str(workspace), "--play-profile", profile.profile_id, "--virtual-camera"
    ]) == 0
    assert captured["tool"] == "run_avatar_profile.py"
    assert "--virtual-camera" in captured["arguments"]
    assert captured["project_root"] == workspace.resolve()
