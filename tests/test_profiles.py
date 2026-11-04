from __future__ import annotations

from pathlib import Path

from avatar_controller.studio.profiles import AvatarProfileStore, ProfileStatus
from avatar_controller.video_io import VideoMetadata


def test_imported_profile_is_stored_only_in_the_local_workspace(tmp_path: Path) -> None:
    video = tmp_path / "avatar.mp4"
    video.write_bytes(b"not-a-real-video")
    metadata = VideoMetadata(
        path=video,
        width=1280,
        height=720,
        fps=30.0,
        frame_count=300,
        duration_seconds=10.0,
        codec="h264",
    )
    store = AvatarProfileStore(tmp_path / "workspace" / "data" / "studio")
    profile = store.create_imported_profile(video, metadata, name="Demo")
    assert profile.status is ProfileStatus.NEEDS_ANALYSIS
    assert profile.config_path.is_file()
    assert profile.config_path.parent.is_relative_to(tmp_path / "workspace")
    assert store.get_profile(profile.profile_id).video_path == video.resolve()


def test_status_changes_keep_the_same_local_profile(tmp_path: Path) -> None:
    video = tmp_path / "avatar.mp4"
    video.write_bytes(b"video")
    metadata = VideoMetadata(video, 640, 480, 25.0, 100, 4.0, None)
    store = AvatarProfileStore(tmp_path / "data" / "studio")
    profile = store.create_imported_profile(video, metadata)
    updated = store.update_status(profile.profile_id, ProfileStatus.READY)
    assert updated.status is ProfileStatus.READY
    assert store.get_profile(profile.profile_id).status is ProfileStatus.READY
