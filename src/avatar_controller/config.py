from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when application configuration is missing or invalid."""


@dataclass(frozen=True)
class VideoConfig:
    path: Path
    preserve_resolution: bool = True
    preserve_fps: bool = True
    preload_segments: bool = True


@dataclass(frozen=True)
class PlaybackConfig:
    start_state: str = "CENTER"
    command_queue: bool = True
    max_queue_size: int = 2
    idle_loop_crossfade_frames: int = 6
    transition_crossfade_frames: int = 4
    allow_experimental_optical_flow: bool = False


@dataclass(frozen=True)
class ControlsConfig:
    left: str = "left"
    right: str = "right"
    up: str = "up"
    down: str = "down"
    recenter: str = "r"
    pause: str = "space"
    quit: str = "esc"
    diagnostics: str = "d"


@dataclass(frozen=True)
class OutputConfig:
    mode: str = "window"
    fullscreen: bool = False
    virtual_camera_enabled: bool = False
    virtual_camera_backend: str = "obs"


@dataclass(frozen=True)
class QualityConfig:
    allow_resize: bool = False
    allow_color_correction: bool = False
    allow_face_warping: bool = False
    allow_background_modification: bool = False


@dataclass(frozen=True)
class AppConfig:
    video: VideoConfig
    playback: PlaybackConfig
    controls: ControlsConfig
    output: OutputConfig
    quality: QualityConfig


def load_config(config_path: Path | str) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must contain a YAML mapping: {path}")

    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    video_raw = _section(raw, "video")
    playback_raw = _section(raw, "playback")
    controls_raw = _section(raw, "controls")
    output_raw = _section(raw, "output")
    quality_raw = _section(raw, "quality")

    video = VideoConfig(
        path=_path_value(video_raw.get("path"), "video.path"),
        preserve_resolution=_bool_value(
            video_raw.get("preserve_resolution", True), "video.preserve_resolution"
        ),
        preserve_fps=_bool_value(video_raw.get("preserve_fps", True), "video.preserve_fps"),
        preload_segments=_bool_value(
            video_raw.get("preload_segments", True), "video.preload_segments"
        ),
    )

    playback = PlaybackConfig(
        start_state=_str_value(playback_raw.get("start_state", "CENTER"), "playback.start_state"),
        command_queue=_bool_value(playback_raw.get("command_queue", True), "playback.command_queue"),
        max_queue_size=_int_value(playback_raw.get("max_queue_size", 2), "playback.max_queue_size"),
        idle_loop_crossfade_frames=_int_value(
            playback_raw.get("idle_loop_crossfade_frames", 6),
            "playback.idle_loop_crossfade_frames",
        ),
        transition_crossfade_frames=_int_value(
            playback_raw.get("transition_crossfade_frames", 4),
            "playback.transition_crossfade_frames",
        ),
        allow_experimental_optical_flow=_bool_value(
            playback_raw.get("allow_experimental_optical_flow", False),
            "playback.allow_experimental_optical_flow",
        ),
    )

    controls = ControlsConfig(
        left=_str_value(controls_raw.get("left", "left"), "controls.left"),
        right=_str_value(controls_raw.get("right", "right"), "controls.right"),
        up=_str_value(controls_raw.get("up", "up"), "controls.up"),
        down=_str_value(controls_raw.get("down", "down"), "controls.down"),
        recenter=_str_value(controls_raw.get("recenter", "r"), "controls.recenter"),
        pause=_str_value(controls_raw.get("pause", "space"), "controls.pause"),
        quit=_str_value(controls_raw.get("quit", "esc"), "controls.quit"),
        diagnostics=_str_value(controls_raw.get("diagnostics", "d"), "controls.diagnostics"),
    )

    output = OutputConfig(
        mode=_str_value(output_raw.get("mode", "window"), "output.mode"),
        fullscreen=_bool_value(output_raw.get("fullscreen", False), "output.fullscreen"),
        virtual_camera_enabled=_bool_value(
            output_raw.get("virtual_camera_enabled", False),
            "output.virtual_camera_enabled",
        ),
        virtual_camera_backend=_str_value(
            output_raw.get("virtual_camera_backend", "obs"),
            "output.virtual_camera_backend",
        ),
    )

    quality = QualityConfig(
        allow_resize=_bool_value(quality_raw.get("allow_resize", False), "quality.allow_resize"),
        allow_color_correction=_bool_value(
            quality_raw.get("allow_color_correction", False),
            "quality.allow_color_correction",
        ),
        allow_face_warping=_bool_value(
            quality_raw.get("allow_face_warping", False),
            "quality.allow_face_warping",
        ),
        allow_background_modification=_bool_value(
            quality_raw.get("allow_background_modification", False),
            "quality.allow_background_modification",
        ),
    )

    _validate_playback(playback)
    return AppConfig(video=video, playback=playback, controls=controls, output=output, quality=quality)


def validate_video_path(video_path: Path) -> Path:
    path = Path(video_path)
    if not path.exists():
        raise ConfigError(f"Video file does not exist: {path}")
    if not path.is_file():
        raise ConfigError(f"Video path is not a file: {path}")
    return path


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Config section '{name}' must be a mapping")
    return value


def _path_value(value: Any, name: str) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    raise ConfigError(f"Config value '{name}' must be a non-empty path string")


def _str_value(value: Any, name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    raise ConfigError(f"Config value '{name}' must be a non-empty string")


def _bool_value(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ConfigError(f"Config value '{name}' must be true or false")


def _int_value(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Config value '{name}' must be an integer")
    return value


def _validate_playback(playback: PlaybackConfig) -> None:
    if playback.start_state not in {"CENTER", "LEFT", "RIGHT", "UP", "DOWN"}:
        raise ConfigError(
            "Config value 'playback.start_state' must be one of CENTER, LEFT, RIGHT, UP, DOWN"
        )
    if playback.max_queue_size < 0:
        raise ConfigError("Config value 'playback.max_queue_size' must be >= 0")
    if playback.idle_loop_crossfade_frames < 0:
        raise ConfigError("Config value 'playback.idle_loop_crossfade_frames' must be >= 0")
    if playback.transition_crossfade_frames < 0:
        raise ConfigError("Config value 'playback.transition_crossfade_frames' must be >= 0")
