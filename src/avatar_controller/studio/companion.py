from __future__ import annotations

from pathlib import Path

from avatar_controller.config import load_config, validate_video_path
from avatar_controller.segments import load_segments
from avatar_controller.studio.commands import StudioCommandBuilder
from avatar_controller.studio.profiles import AvatarProfileStore, ProfileStatus, StudioProfileError


PUBLIC_RUNTIME_MARKER = {
    "schema_version": 2,
    "runtime": "avatar-studio-public",
    "profile_contract": "reviewed-profile-v1",
}


def reviewed_profile_arguments(
    workspace: Path, profile_id: str, *, virtual_camera: bool = True
) -> tuple[str, ...]:
    """Resolve an explicit reviewed profile; never pick a user's avatar implicitly."""

    profile = AvatarProfileStore(workspace / "data" / "studio").get_profile(profile_id)
    if profile.status is not ProfileStatus.READY:
        raise StudioProfileError("El perfil debe estar revisado y listo antes de conectarlo")
    root = workspace.resolve()
    for path in (profile.config_path, profile.segments_path):
        if not path.resolve().is_relative_to(root):
            raise StudioProfileError("El perfil contiene archivos fuera de su espacio de trabajo")
    config = load_config(profile.config_path)
    video = validate_video_path(config.video.path).resolve()
    segments = load_segments(profile.segments_path)
    if video != profile.video_path.resolve() or video != segments.video_path.resolve():
        raise StudioProfileError("El vídeo, el perfil y sus segmentos no coinciden")
    command = StudioCommandBuilder(workspace, frozen=True).preview(
        profile, virtual_camera=virtual_camera
    )
    return command.arguments
