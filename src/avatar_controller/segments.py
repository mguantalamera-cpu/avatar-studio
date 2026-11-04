from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


REQUIRED_SEGMENTS: tuple[str, ...] = (
    "CENTER_IDLE",
    "CENTER_TO_LEFT",
    "LEFT_IDLE",
    "LEFT_TO_CENTER",
    "CENTER_TO_RIGHT",
    "RIGHT_IDLE",
    "RIGHT_TO_CENTER",
    "CENTER_TO_UP",
    "UP_IDLE",
    "UP_TO_CENTER",
    "CENTER_TO_DOWN",
    "DOWN_IDLE",
    "DOWN_TO_CENTER",
)

# The stable file/UI order above is kept for backwards compatibility.  Recording
# order is a separate contract: the guided capture asks for RIGHT before LEFT.
TEMPORAL_SEGMENT_ORDER: tuple[str, ...] = (
    "CENTER_IDLE",
    "CENTER_TO_RIGHT",
    "RIGHT_IDLE",
    "RIGHT_TO_CENTER",
    "CENTER_TO_LEFT",
    "LEFT_IDLE",
    "LEFT_TO_CENTER",
    "CENTER_TO_UP",
    "UP_IDLE",
    "UP_TO_CENTER",
    "CENTER_TO_DOWN",
    "DOWN_IDLE",
    "DOWN_TO_CENTER",
)

KNOWN_SEGMENTS: tuple[str, ...] = REQUIRED_SEGMENTS


class SegmentError(ValueError):
    """Raised when segment YAML cannot be loaded or represented."""


@dataclass
class SegmentMark:
    name: str
    start_frame: int | None = None
    end_frame: int | None = None
    notes: str = ""

    @property
    def frame_count(self) -> int | None:
        if self.start_frame is None or self.end_frame is None:
            return None
        return self.end_frame - self.start_frame + 1

    @property
    def is_complete(self) -> bool:
        return self.start_frame is not None and self.end_frame is not None

    @property
    def is_idle(self) -> bool:
        return self.name.endswith("_IDLE")


@dataclass
class SegmentSet:
    version: int
    video_path: Path
    width: int
    height: int
    fps: float
    total_frames: int
    segments: dict[str, SegmentMark] = field(default_factory=dict)

    def to_yaml_data(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "video_path": _path_to_yaml(self.video_path),
            "video": {
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "total_frames": self.total_frames,
            },
            "segments": {
                name: {
                    "start_frame": mark.start_frame,
                    "end_frame": mark.end_frame,
                    "notes": mark.notes,
                }
                for name, mark in self.segments.items()
            },
        }


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    segment: str | None = None

    def format(self) -> str:
        if self.segment:
            return f"{self.segment}: {self.message}"
        return self.message


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def is_complete(self) -> bool:
        return not any("incomplete" in issue.message.lower() for issue in self.errors)


def create_empty_segment_set(video_path: Path | str, metadata: Any) -> SegmentSet:
    return SegmentSet(
        version=1,
        video_path=Path(video_path),
        width=int(_metadata_value(metadata, "width")),
        height=int(_metadata_value(metadata, "height")),
        fps=float(_metadata_value(metadata, "fps")),
        total_frames=int(_metadata_value(metadata, "total_frames", "frame_count")),
        segments={name: SegmentMark(name=name) for name in REQUIRED_SEGMENTS},
    )


def load_segments(path: Path | str) -> SegmentSet:
    segments_path = Path(path)
    if not segments_path.exists():
        raise SegmentError(f"Segments file does not exist: {segments_path}")

    with segments_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise SegmentError(f"Segments file must contain a YAML mapping: {segments_path}")

    version = int(raw.get("version", 1))
    video_path = _required_path(raw, "video_path")
    video = raw.get("video")
    if not isinstance(video, dict):
        raise SegmentError("Segments file requires a 'video' mapping")

    raw_segments = raw.get("segments")
    if not isinstance(raw_segments, dict):
        raise SegmentError("Segments file requires a 'segments' mapping")

    parsed_segments: dict[str, SegmentMark] = {}
    for name, mark_raw in raw_segments.items():
        if not isinstance(name, str):
            raise SegmentError("Segment names must be strings")
        if mark_raw is None:
            mark_raw = {}
        if not isinstance(mark_raw, dict):
            raise SegmentError(f"Segment '{name}' must be a mapping")
        parsed_segments[name] = SegmentMark(
            name=name,
            start_frame=_optional_int(mark_raw.get("start_frame"), f"{name}.start_frame"),
            end_frame=_optional_int(mark_raw.get("end_frame"), f"{name}.end_frame"),
            notes=str(mark_raw.get("notes") or ""),
        )

    return SegmentSet(
        version=version,
        video_path=video_path,
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=float(video.get("fps", 0.0)),
        total_frames=int(video.get("total_frames", 0)),
        segments=parsed_segments,
    )


def save_segments(path: Path | str, segment_set: SegmentSet) -> Path:
    segments_path = Path(path)
    segments_path.parent.mkdir(parents=True, exist_ok=True)
    backup_existing_segments_file(segments_path)

    with segments_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            segment_set.to_yaml_data(),
            handle,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    return segments_path


def validate_segments(segment_set: SegmentSet, total_frames: int | None = None) -> ValidationResult:
    frame_limit = int(total_frames if total_frames is not None else segment_set.total_frames)
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    missing = [name for name in REQUIRED_SEGMENTS if name not in segment_set.segments]
    for name in missing:
        errors.append(ValidationIssue("missing required segment", name))

    extra = [name for name in segment_set.segments if name not in KNOWN_SEGMENTS]
    for name in extra:
        warnings.append(ValidationIssue("unknown segment name will be ignored by playback", name))

    complete_for_order: list[tuple[str, int, int]] = []
    for name in REQUIRED_SEGMENTS:
        mark = segment_set.segments.get(name)
        if mark is None:
            continue

        if mark.start_frame is None or mark.end_frame is None:
            errors.append(ValidationIssue("incomplete: start_frame or end_frame is null", name))
            continue

        if isinstance(mark.start_frame, bool) or not isinstance(mark.start_frame, int):
            errors.append(ValidationIssue("start_frame must be an integer or null", name))
            continue
        if isinstance(mark.end_frame, bool) or not isinstance(mark.end_frame, int):
            errors.append(ValidationIssue("end_frame must be an integer or null", name))
            continue

        if mark.start_frame < 0:
            errors.append(ValidationIssue("start_frame must be >= 0", name))
        if mark.end_frame >= frame_limit:
            errors.append(
                ValidationIssue(f"end_frame must be < total_frames ({frame_limit})", name)
            )
        if mark.start_frame > mark.end_frame:
            errors.append(ValidationIssue("start_frame must be <= end_frame", name))
            continue

        frame_count = mark.frame_count
        if frame_count is None:
            continue
        if frame_count < 2:
            errors.append(ValidationIssue("segment must contain at least 2 frames", name))
        if mark.is_idle and frame_count < 15:
            errors.append(ValidationIssue("IDLE segment must contain at least 15 frames", name))
        if not mark.is_idle and frame_count < 3:
            errors.append(ValidationIssue("transition segment must contain at least 3 frames", name))

        complete_for_order.append((name, mark.start_frame, mark.end_frame))

    warnings.extend(_overlap_warnings(complete_for_order))
    complete_by_name = {
        name: (name, start_frame, end_frame)
        for name, start_frame, end_frame in complete_for_order
    }
    temporal_segments = [
        complete_by_name[name]
        for name in TEMPORAL_SEGMENT_ORDER
        if name in complete_by_name
    ]
    warnings.extend(_temporal_order_warnings(temporal_segments))
    return ValidationResult(errors=tuple(errors), warnings=tuple(warnings))


def backup_existing_segments_file(path: Path | str) -> Path | None:
    segments_path = Path(path)
    if not segments_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = segments_path.with_name(
        f"{segments_path.stem}.backup_{timestamp}{segments_path.suffix}"
    )
    counter = 1
    while backup_path.exists():
        backup_path = segments_path.with_name(
            f"{segments_path.stem}.backup_{timestamp}_{counter}{segments_path.suffix}"
        )
        counter += 1

    shutil.copy2(segments_path, backup_path)
    return backup_path


def _overlap_warnings(segments: list[tuple[str, int, int]]) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []
    ordered_by_start = sorted(segments, key=lambda item: (item[1], item[2]))
    previous: tuple[str, int, int] | None = None
    for current in ordered_by_start:
        if previous and current[1] <= previous[2]:
            warnings.append(
                ValidationIssue(
                    f"overlaps {previous[0]} ({previous[1]}-{previous[2]})",
                    current[0],
                )
            )
        previous = current
    return warnings


def _temporal_order_warnings(segments: list[tuple[str, int, int]]) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []
    last_start: int | None = None
    last_name: str | None = None
    for name, start_frame, _end_frame in segments:
        if last_start is not None and start_frame < last_start:
            warnings.append(
                ValidationIssue(
                    f"starts before previous required segment {last_name}",
                    name,
                )
            )
        last_start = start_frame
        last_name = name
    return warnings


def _metadata_value(metadata: Any, *names: str) -> Any:
    for name in names:
        if isinstance(metadata, dict) and name in metadata:
            return metadata[name]
        if hasattr(metadata, name):
            return getattr(metadata, name)
    joined = " or ".join(names)
    raise SegmentError(f"Metadata is missing {joined}")


def _required_path(raw: dict[str, Any], key: str) -> Path:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SegmentError(f"Segments file requires a non-empty '{key}' string")
    return Path(value)


def _optional_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SegmentError(f"{name} must be an integer or null")
    return value


def _path_to_yaml(path: Path) -> str:
    return path.as_posix()
