from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable


MINIMUM_DELTA_SAMPLES = 3
CFR_MAX_RELATIVE_DEVIATION = 0.001
NEAR_CFR_MAX_RELATIVE_DEVIATION = 0.05
NEAR_CFR_MAX_COEFFICIENT_OF_VARIATION = 0.02


class TimingClassification(StrEnum):
    """Timing regularity inferred from presentation timestamps or frame deltas."""

    CFR = "CFR"
    NEAR_CFR = "NEAR_CFR"
    VFR = "VFR"
    INVALID_TIMESTAMPS = "INVALID_TIMESTAMPS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class VideoTimingReport:
    """Non-destructive timing observations for one video stream."""

    path: Path
    classification: TimingClassification
    frames_observed: int
    median_delta_seconds: float | None
    median_fps: float | None
    nominal_fps: float | None
    warning: str | None = None

    @property
    def observed_frames(self) -> int:
        """Compatibility alias using natural English field order."""

        return self.frames_observed

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "classification": self.classification.value,
            "frames_observed": self.frames_observed,
            "median_delta_seconds": self.median_delta_seconds,
            "median_fps": self.median_fps,
            "nominal_fps": self.nominal_fps,
            "warning": self.warning,
        }


def classify_timing_from_pts(
    pts: Iterable[Real] | None,
) -> TimingClassification:
    """Classify timing from ordered presentation timestamps.

    PTS values may use any time base. They must be finite and strictly increasing.
    At least four timestamps (three deltas) are required for a useful result.
    """

    values = _finite_values(pts)
    if values is None:
        return TimingClassification.INVALID_TIMESTAMPS

    deltas = tuple(current - previous for previous, current in zip(values, values[1:]))
    if any(delta <= 0.0 for delta in deltas):
        return TimingClassification.INVALID_TIMESTAMPS
    if len(values) < MINIMUM_DELTA_SAMPLES + 1:
        return TimingClassification.UNKNOWN
    return _classify_validated_deltas(deltas)


def classify_timing_from_deltas(
    deltas: Iterable[Real] | None,
) -> TimingClassification:
    """Classify timing from positive frame-to-frame timestamp deltas.

    Constant timing permits at most 0.1% deviation from the median delta.
    Near-constant timing permits at most 5% deviation and a 2% coefficient of
    variation. Larger variation is classified as VFR.
    """

    values = _finite_values(deltas)
    if values is None:
        return TimingClassification.INVALID_TIMESTAMPS
    if any(delta <= 0.0 for delta in values):
        return TimingClassification.INVALID_TIMESTAMPS
    if len(values) < MINIMUM_DELTA_SAMPLES:
        return TimingClassification.UNKNOWN
    return _classify_validated_deltas(values)


def inspect_video_timing(video_path: Path | str) -> VideoTimingReport:
    """Decode video timestamps with PyAV without modifying the source file.

    PyAV is imported lazily. Dependency, container, stream, and decode failures
    are represented by an ``UNKNOWN`` report instead of escaping this function.
    """

    path = Path(video_path)
    try:
        av = _load_av()
    except Exception as exc:
        return _build_report(
            path=path,
            classification=TimingClassification.UNKNOWN,
            frames_observed=0,
            timestamps=(),
            nominal_fps=None,
            warning=_exception_warning("PyAV is unavailable", exc),
        )

    container: Any | None = None
    frames_observed = 0
    timestamps: list[float] = []
    nominal_fps: float | None = None
    try:
        container = av.open(str(path))
        video_streams = tuple(getattr(container.streams, "video", ()))
        if not video_streams:
            return _build_report(
                path=path,
                classification=TimingClassification.UNKNOWN,
                frames_observed=0,
                timestamps=(),
                nominal_fps=None,
                warning="No video stream was found.",
            )

        stream = video_streams[0]
        nominal_fps = _nominal_fps(stream)
        missing_timestamps = 0
        for frame in container.decode(stream):
            frames_observed += 1
            timestamp = _frame_timestamp_seconds(frame, stream)
            if timestamp is None:
                missing_timestamps += 1
            else:
                timestamps.append(timestamp)

        if missing_timestamps:
            return _build_report(
                path=path,
                classification=TimingClassification.UNKNOWN,
                frames_observed=frames_observed,
                timestamps=(),
                nominal_fps=nominal_fps,
                warning=(
                    f"{missing_timestamps} of {frames_observed} decoded video frames "
                    "had no usable timestamp."
                ),
            )

        classification = classify_timing_from_pts(timestamps)
        return _build_report(
            path=path,
            classification=classification,
            frames_observed=frames_observed,
            timestamps=timestamps,
            nominal_fps=nominal_fps,
            warning=_classification_warning(classification, frames_observed),
        )
    except Exception as exc:
        return _build_report(
            path=path,
            classification=TimingClassification.UNKNOWN,
            frames_observed=frames_observed,
            timestamps=timestamps,
            nominal_fps=nominal_fps,
            warning=_exception_warning("PyAV could not inspect video timing", exc),
        )
    finally:
        _close_container(container)


def save_video_timing_report(
    report: VideoTimingReport,
    output_path: Path | str,
) -> Path:
    """Atomically write a timing report as JSON and return its destination."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        temporary = NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temporary_path = Path(temporary.name)
        with temporary as handle:
            json.dump(report.to_dict(), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return path


def _finite_values(values: Iterable[Real] | None) -> tuple[float, ...] | None:
    if values is None:
        return ()

    parsed: list[float] = []
    try:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, Real):
                return None
            parsed_value = float(value)
            if not math.isfinite(parsed_value):
                return None
            parsed.append(parsed_value)
    except TypeError:
        return None
    return tuple(parsed)


def _classify_validated_deltas(deltas: tuple[float, ...]) -> TimingClassification:
    if any(delta <= 0.0 for delta in deltas):
        return TimingClassification.INVALID_TIMESTAMPS

    median_delta = statistics.median(deltas)
    max_relative_deviation = max(
        abs(delta - median_delta) / median_delta for delta in deltas
    )
    if max_relative_deviation <= CFR_MAX_RELATIVE_DEVIATION:
        return TimingClassification.CFR

    mean_delta = math.fsum(deltas) / len(deltas)
    variance = math.fsum((delta - mean_delta) ** 2 for delta in deltas) / len(deltas)
    coefficient_of_variation = math.sqrt(variance) / mean_delta
    if (
        max_relative_deviation <= NEAR_CFR_MAX_RELATIVE_DEVIATION
        and coefficient_of_variation <= NEAR_CFR_MAX_COEFFICIENT_OF_VARIATION
    ):
        return TimingClassification.NEAR_CFR
    return TimingClassification.VFR


def _build_report(
    *,
    path: Path,
    classification: TimingClassification,
    frames_observed: int,
    timestamps: Iterable[Real],
    nominal_fps: float | None,
    warning: str | None,
) -> VideoTimingReport:
    median_delta_seconds, median_fps = _median_timing(timestamps)
    return VideoTimingReport(
        path=path,
        classification=classification,
        frames_observed=frames_observed,
        median_delta_seconds=median_delta_seconds,
        median_fps=median_fps,
        nominal_fps=nominal_fps,
        warning=warning,
    )


def _median_timing(
    timestamps: Iterable[Real],
) -> tuple[float | None, float | None]:
    values = _finite_values(timestamps)
    if values is None or len(values) < 2:
        return None, None
    deltas = tuple(current - previous for previous, current in zip(values, values[1:]))
    if any(delta <= 0.0 for delta in deltas):
        return None, None
    median_delta = statistics.median(deltas)
    return median_delta, 1.0 / median_delta


def _nominal_fps(stream: Any) -> float | None:
    for attribute in ("average_rate", "base_rate", "guessed_rate"):
        try:
            value = getattr(stream, attribute, None)
        except Exception:
            continue
        parsed = _positive_finite_float(value)
        if parsed is not None:
            return parsed
    return None


def _frame_timestamp_seconds(frame: Any, stream: Any) -> float | None:
    try:
        frame_time = getattr(frame, "time", None)
    except Exception:
        frame_time = None
    parsed_time = _finite_float(frame_time)
    if parsed_time is not None:
        return parsed_time

    try:
        pts = getattr(frame, "pts", None)
        time_base = getattr(frame, "time_base", None)
        if time_base is None:
            time_base = getattr(stream, "time_base", None)
    except Exception:
        return None
    parsed_pts = _finite_float(pts)
    parsed_time_base = _positive_finite_float(time_base)
    if parsed_pts is None or parsed_time_base is None:
        return None
    return parsed_pts * parsed_time_base


def _finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _positive_finite_float(value: Any) -> float | None:
    parsed = _finite_float(value)
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


def _classification_warning(
    classification: TimingClassification,
    frames_observed: int,
) -> str | None:
    if classification is TimingClassification.NEAR_CFR:
        return "Minor video timestamp jitter was detected."
    if classification is TimingClassification.VFR:
        return "Variable video frame timing was detected."
    if classification is TimingClassification.INVALID_TIMESTAMPS:
        return "Video timestamps were duplicated, decreasing, or otherwise invalid."
    if classification is TimingClassification.UNKNOWN:
        return (
            f"Only {frames_observed} timestamped video frames were observed; "
            f"at least {MINIMUM_DELTA_SAMPLES + 1} are required."
        )
    return None


def _exception_warning(prefix: str, exc: Exception) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{prefix}: {detail}"
    return f"{prefix}: {type(exc).__name__}"


def _close_container(container: Any | None) -> None:
    if container is None:
        return
    try:
        container.close()
    except Exception:
        pass


def _load_av() -> Any:
    import av

    return av
