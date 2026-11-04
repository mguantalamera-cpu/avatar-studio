from __future__ import annotations

import json
from dataclasses import dataclass

from avatar_controller.segments import REQUIRED_SEGMENTS, load_segments
from avatar_controller.studio.profiles import AvatarProfile


@dataclass(frozen=True)
class SegmentAnalysisSummary:
    name: str
    start_frame: int | None
    end_frame: int | None
    duration_seconds: float | None
    confidence: float | None
    warnings: tuple[str, ...]

    @property
    def is_detected(self) -> bool:
        return self.start_frame is not None and self.end_frame is not None


@dataclass(frozen=True)
class ProfileAnalysisSummary:
    segments: tuple[SegmentAnalysisSummary, ...]
    warnings: tuple[str, ...]
    method: str | None

    @property
    def detected_count(self) -> int:
        return sum(segment.is_detected for segment in self.segments)

    @property
    def required_count(self) -> int:
        return len(self.segments)

    @property
    def is_complete(self) -> bool:
        return self.detected_count == self.required_count


def load_profile_analysis(profile: AvatarProfile) -> ProfileAnalysisSummary:
    if _analysis_report_is_current(profile):
        try:
            raw = json.loads(profile.report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        raw_segments = raw.get("segments")
        if isinstance(raw_segments, dict):
            method_raw = raw.get("method")
            method = method_raw.get("name") if isinstance(method_raw, dict) else None
            return ProfileAnalysisSummary(
                segments=tuple(
                    _summary_from_report(name, raw_segments.get(name), profile.fps)
                    for name in REQUIRED_SEGMENTS
                ),
                warnings=tuple(str(item) for item in raw.get("warnings", []) if item),
                method=str(method) if method else None,
            )

    if profile.segments_path.exists():
        segment_set = load_segments(profile.segments_path)
        segments = []
        for name in REQUIRED_SEGMENTS:
            mark = segment_set.segments.get(name)
            start = mark.start_frame if mark else None
            end = mark.end_frame if mark else None
            duration = (
                (end - start + 1) / profile.fps
                if start is not None and end is not None and profile.fps > 0
                else None
            )
            segments.append(
                SegmentAnalysisSummary(
                    name=name,
                    start_frame=start,
                    end_frame=end,
                    duration_seconds=duration,
                    confidence=None,
                    warnings=(),
                )
            )
        return ProfileAnalysisSummary(tuple(segments), (), "reviewed configuration")

    return ProfileAnalysisSummary(
        segments=tuple(
            SegmentAnalysisSummary(name, None, None, None, None, ())
            for name in REQUIRED_SEGMENTS
        ),
        warnings=(),
        method=None,
    )


def _analysis_report_is_current(profile: AvatarProfile) -> bool:
    if not profile.report_path.exists():
        return False
    if not profile.segments_path.exists():
        return True
    try:
        return (
            profile.report_path.stat().st_mtime_ns
            >= profile.segments_path.stat().st_mtime_ns
        )
    except OSError:
        return True


def _summary_from_report(
    name: str,
    raw: object,
    fps: float,
) -> SegmentAnalysisSummary:
    details = raw if isinstance(raw, dict) else {}
    start = _optional_int(details.get("start_frame"))
    end = _optional_int(details.get("end_frame"))
    confidence = details.get("confidence")
    parsed_confidence = (
        float(confidence) if isinstance(confidence, (float, int)) and not isinstance(confidence, bool) else None
    )
    duration = (
        (end - start + 1) / fps
        if start is not None and end is not None and fps > 0
        else None
    )
    warnings = details.get("warnings", [])
    return SegmentAnalysisSummary(
        name=name,
        start_frame=start,
        end_frame=end,
        duration_seconds=duration,
        confidence=parsed_confidence,
        warnings=tuple(str(item) for item in warnings if item) if isinstance(warnings, list) else (),
    )


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None
