from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from avatar_controller.video_io import VideoMetadata


CATALOG_SCHEMA_VERSION = 1
SUPPORTED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".avi", ".webm"})


class StudioProfileError(ValueError):
    """Raised when an Avatar Studio profile cannot be created or loaded."""


class ProfileStatus(StrEnum):
    NEEDS_ANALYSIS = "needs_analysis"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"


@dataclass(frozen=True)
class AvatarProfile:
    profile_id: str
    name: str
    status: ProfileStatus
    video_path: Path
    config_path: Path
    segments_path: Path
    report_path: Path
    created_at: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        for key in ("video_path", "config_path", "segments_path", "report_path"):
            data[key] = str(data[key])
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AvatarProfile:
        try:
            return cls(
                profile_id=str(raw["profile_id"]),
                name=str(raw["name"]),
                status=ProfileStatus(str(raw["status"])),
                video_path=Path(str(raw["video_path"])),
                config_path=Path(str(raw["config_path"])),
                segments_path=Path(str(raw["segments_path"])),
                report_path=Path(str(raw["report_path"])),
                created_at=str(raw["created_at"]),
                width=int(raw["width"]),
                height=int(raw["height"]),
                fps=float(raw["fps"]),
                frame_count=int(raw["frame_count"]),
                duration_seconds=float(raw["duration_seconds"]),
                codec=str(raw["codec"]) if raw.get("codec") else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StudioProfileError("Avatar Studio catalog contains an invalid profile") from exc


class AvatarProfileStore:
    def __init__(self, studio_root: Path | str) -> None:
        self.studio_root = Path(studio_root)
        self.profiles_root = self.studio_root / "profiles"
        self.catalog_path = self.studio_root / "catalog.json"

    def list_profiles(self) -> list[AvatarProfile]:
        return sorted(
            self._load_profiles().values(),
            key=lambda profile: (profile.created_at, profile.name.lower()),
        )

    def get_profile(self, profile_id: str) -> AvatarProfile:
        profile = self._load_profiles().get(profile_id)
        if profile is None:
            raise StudioProfileError(f"Avatar profile does not exist: {profile_id}")
        return profile

    def upsert_profile(self, profile: AvatarProfile) -> AvatarProfile:
        profiles = self._load_profiles()
        profiles[profile.profile_id] = profile
        self._save_profiles(profiles)
        return profile

    def update_status(self, profile_id: str, status: ProfileStatus) -> AvatarProfile:
        current = self.get_profile(profile_id)
        return self.upsert_profile(AvatarProfile(**{**current.__dict__, "status": status}))

    def invalidate_continuity_after_segment_edit(self, profile_id: str) -> AvatarProfile:
        """Mark edited segments for review without modifying the source video."""

        return self.update_status(profile_id, ProfileStatus.REVIEW_REQUIRED)

    def create_imported_profile(
        self,
        video_path: Path | str,
        metadata: VideoMetadata,
        name: str | None = None,
    ) -> AvatarProfile:
        path = Path(video_path).resolve()
        if not path.exists() or not path.is_file():
            raise StudioProfileError(f"Video file does not exist: {path}")
        if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            raise StudioProfileError(
                f"Unsupported video format '{path.suffix}'. Use MP4, MOV, MKV, AVI or WEBM."
            )

        profile_id = self._profile_id(path)
        existing = self._load_profiles().get(profile_id)
        if existing is not None:
            return existing

        profile_root = self.profiles_root / profile_id
        config_path = profile_root / "default.yaml"
        segments_path = profile_root / "segments.auto.yaml"
        report_path = profile_root / "analysis_report.json"
        profile_root.mkdir(parents=True, exist_ok=True)
        self._write_yaml(config_path, self._default_config(path))
        self._write_json(profile_root / "video_metadata.json", metadata.to_dict())
        profile = AvatarProfile(
            profile_id=profile_id,
            name=(name or path.stem.replace("_", " ").strip() or "Nuevo avatar"),
            status=ProfileStatus.NEEDS_ANALYSIS,
            video_path=path,
            config_path=config_path,
            segments_path=segments_path,
            report_path=report_path,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            width=metadata.width,
            height=metadata.height,
            fps=metadata.fps,
            frame_count=metadata.frame_count,
            duration_seconds=metadata.duration_seconds,
            codec=metadata.codec,
        )
        return self.upsert_profile(profile)

    def _load_profiles(self) -> dict[str, AvatarProfile]:
        if not self.catalog_path.exists():
            return {}
        try:
            raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StudioProfileError(
                f"Could not read Avatar Studio catalog: {self.catalog_path}"
            ) from exc
        if raw.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise StudioProfileError("Unsupported Avatar Studio catalog version")
        profile_items = raw.get("profiles", [])
        if not isinstance(profile_items, list):
            raise StudioProfileError("Avatar Studio catalog profiles must be a list")
        profiles = [AvatarProfile.from_dict(item) for item in profile_items]
        return {profile.profile_id: profile for profile in profiles}

    def _save_profiles(self, profiles: dict[str, AvatarProfile]) -> None:
        self._write_json(
            self.catalog_path,
            {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "profiles": [profile.to_dict() for profile in profiles.values()],
            },
        )

    @staticmethod
    def _profile_id(path: Path) -> str:
        stat = path.stat()
        identity = f"{path.as_posix().lower()}|{stat.st_size}|{stat.st_mtime_ns}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
        slug = "".join(character.lower() if character.isalnum() else "-" for character in path.stem)
        slug = "-".join(filter(None, slug.split("-")))[:36] or "avatar"
        return f"{slug}-{digest}"

    @staticmethod
    def _default_config(video_path: Path) -> dict[str, Any]:
        return {
            "video": {
                "path": video_path.as_posix(),
                "preserve_resolution": True,
                "preserve_fps": True,
                "preload_segments": True,
            },
            "playback": {
                "start_state": "CENTER",
                "command_queue": True,
                "max_queue_size": 2,
                "idle_loop_crossfade_frames": 6,
                "transition_crossfade_frames": 4,
                "allow_experimental_optical_flow": False,
            },
            "controls": {
                "left": "left",
                "right": "right",
                "up": "up",
                "down": "down",
                "recenter": "r",
                "pause": "space",
                "quit": "esc",
                "diagnostics": "d",
            },
            "output": {
                "mode": "window",
                "fullscreen": False,
                "virtual_camera_enabled": False,
                "virtual_camera_backend": "obs",
            },
            "quality": {
                "allow_resize": False,
                "allow_color_correction": False,
                "allow_face_warping": False,
                "allow_background_modification": False,
            },
        }

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
        temporary.replace(path)
