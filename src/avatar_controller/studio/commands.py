from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from avatar_controller.segments import load_segments, validate_segments
from avatar_controller.studio.profiles import AvatarProfile, ProfileStatus, StudioProfileError


@dataclass(frozen=True)
class StudioCommand:
    program: str
    arguments: tuple[str, ...]


class StudioCommandBuilder:
    def __init__(
        self,
        project_root: Path | str,
        python_executable: str | None = None,
        *,
        frozen: bool | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.python_executable = python_executable or sys.executable
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen

    def analyze(self, profile: AvatarProfile) -> StudioCommand:
        return self._tool(
            "analyze_studio_profile.py",
            "--project-root",
            str(self.project_root),
            "--profile-id",
            profile.profile_id,
        )

    def review(self, profile: AvatarProfile) -> StudioCommand:
        if not profile.segments_path.exists():
            raise StudioProfileError("Analiza este vídeo antes de revisar segmentos")
        return self._tool(
            "preview_segments.py",
            "--config",
            str(profile.config_path),
            "--segments",
            str(profile.segments_path),
        )

    def edit(self, profile: AvatarProfile) -> StudioCommand:
        if not profile.segments_path.exists():
            raise StudioProfileError("Analiza este vídeo antes de editar segmentos")
        return self._tool(
            "mark_segments.py",
            "--config",
            str(profile.config_path),
            "--segments",
            str(profile.segments_path),
        )

    def inspect_timing(
        self,
        profile: AvatarProfile,
        output_path: Path | str,
    ) -> StudioCommand:
        return self._tool(
            "inspect_video_timing.py",
            "--video",
            str(profile.video_path),
            "--output",
            str(output_path),
        )

    def preview(self, profile: AvatarProfile, virtual_camera: bool = False) -> StudioCommand:
        if not profile.segments_path.exists():
            raise StudioProfileError("Analiza este vídeo antes de iniciar la reproducción")
        if virtual_camera and profile.status is not ProfileStatus.READY:
            raise StudioProfileError("Revisa el perfil antes de publicarlo en una cámara virtual")
        segment_set = load_segments(profile.segments_path)
        validation = validate_segments(segment_set, profile.frame_count)
        if validation.errors:
            summary = "; ".join(issue.format() for issue in validation.errors[:3])
            raise StudioProfileError(f"Los segmentos no están listos: {summary}")
        arguments = [
            "--config",
            str(profile.config_path),
            "--segments",
            str(profile.segments_path),
        ]
        if virtual_camera:
            arguments.extend(["--virtual-camera", "--virtual-camera-backend", "obs", "--no-overlay"])
        return self._tool("run_avatar_profile.py", *arguments)

    def _tool(self, name: str, *arguments: str) -> StudioCommand:
        if self.frozen:
            return StudioCommand(self.python_executable, ("--internal-tool", name, *arguments))
        return StudioCommand(self.python_executable, (str(self.project_root / "tools" / name), *arguments))
