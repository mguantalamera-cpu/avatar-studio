from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from avatar_controller.segments import (
    REQUIRED_SEGMENTS,
    SegmentMark,
    SegmentSet,
    create_empty_segment_set,
    validate_segments,
)
from avatar_controller.video_io import VideoIOError, VideoMetadata


DIRECTION_TO_SEGMENTS: dict[str, tuple[str, str, str]] = {
    "LEFT": ("CENTER_TO_LEFT", "LEFT_IDLE", "LEFT_TO_CENTER"),
    "RIGHT": ("CENTER_TO_RIGHT", "RIGHT_IDLE", "RIGHT_TO_CENTER"),
    "UP": ("CENTER_TO_UP", "UP_IDLE", "UP_TO_CENTER"),
    "DOWN": ("CENTER_TO_DOWN", "DOWN_IDLE", "DOWN_TO_CENTER"),
}

EXPECTED_DIRECTION_SEQUENCE: tuple[tuple[str, str, int, float], ...] = (
    ("RIGHT", "x", 1, 16.0),
    ("LEFT", "x", -1, 16.0),
    ("UP", "y", -1, 10.0),
    ("DOWN", "y", 1, 10.0),
)


@dataclass(frozen=True)
class FrameSignals:
    x: list[float]
    y: list[float]
    motion: list[float]
    face_detected: list[bool]
    method: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DirectionCandidate:
    direction: str
    axis: str
    sign: int
    motion_start: int
    hold_start: int
    hold_end: int
    motion_end: int
    peak_frame: int
    peak_offset: float
    threshold: float
    confidence: float
    warnings: tuple[str, ...] = ()

    def to_report(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProposedMark:
    name: str
    start_frame: int | None
    end_frame: int | None
    confidence: float
    source: str
    warnings: tuple[str, ...] = ()

    def to_segment_mark(self) -> SegmentMark:
        if self.start_frame is None or self.end_frame is None:
            note = f"auto draft; confidence {self.confidence:.2f}; needs manual review"
        else:
            note = f"auto draft; confidence {self.confidence:.2f}; review manually"
        if self.warnings:
            note += "; " + "; ".join(self.warnings)
        return SegmentMark(
            name=self.name,
            start_frame=self.start_frame,
            end_frame=self.end_frame,
            notes=note,
        )

    def to_report(self) -> dict[str, Any]:
        return {
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "frame_count": (
                self.end_frame - self.start_frame + 1
                if self.start_frame is not None and self.end_frame is not None
                else None
            ),
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class AutoMarkResult:
    segment_set: SegmentSet
    proposed_marks: dict[str, ProposedMark]
    candidates: dict[str, DirectionCandidate]
    report: dict[str, Any]


def generate_auto_segments(
    video_path: Path | str,
    metadata: VideoMetadata,
    prefer_mediapipe: bool = True,
) -> AutoMarkResult:
    path = Path(video_path)
    signals = collect_frame_signals(path, metadata, prefer_mediapipe=prefer_mediapipe)
    candidates = find_direction_candidates(signals)
    proposed_marks = build_proposed_marks(metadata.frame_count, signals, candidates)
    segment_set = create_empty_segment_set(path, metadata)

    for name in REQUIRED_SEGMENTS:
        proposed = proposed_marks.get(name)
        if proposed is None:
            segment_set.segments[name] = SegmentMark(
                name=name,
                notes="auto draft; confidence 0.00; not detected; needs manual review",
            )
        else:
            segment_set.segments[name] = proposed.to_segment_mark()

    report = build_report(path, metadata, signals, candidates, proposed_marks)
    validation = validate_segments(segment_set, metadata.frame_count)
    report["validation"] = {
        "errors": [issue.format() for issue in validation.errors],
        "warnings": [issue.format() for issue in validation.warnings],
    }
    if validation.warnings:
        report["warnings"].append(
            "The automatic draft is stored in required segment-name order, but detected motion "
            "may occur in a different temporal order in the source video."
        )
    return AutoMarkResult(
        segment_set=segment_set,
        proposed_marks=proposed_marks,
        candidates=candidates,
        report=report,
    )


def collect_frame_signals(
    video_path: Path,
    metadata: VideoMetadata,
    prefer_mediapipe: bool = True,
    analysis_width: int = 640,
) -> FrameSignals:
    warnings: list[str] = []
    if prefer_mediapipe:
        mediapipe_signals = _collect_mediapipe_signals(video_path, metadata, analysis_width)
        if mediapipe_signals is not None:
            return mediapipe_signals
        warnings.append("MediaPipe is not available or did not produce enough landmarks; using OpenCV Haar fallback.")

    haar_signals = _collect_haar_signals(video_path, metadata, analysis_width)
    return FrameSignals(
        x=haar_signals.x,
        y=haar_signals.y,
        motion=haar_signals.motion,
        face_detected=haar_signals.face_detected,
        method=haar_signals.method,
        warnings=warnings + haar_signals.warnings,
    )


def find_direction_candidates(signals: FrameSignals) -> dict[str, DirectionCandidate]:
    x = np.asarray(signals.x, dtype=float)
    y = np.asarray(signals.y, dtype=float)
    detected = np.asarray(signals.face_detected, dtype=bool)

    if len(x) == 0:
        return {}

    frame_count = min(len(x), len(y), len(detected))
    if frame_count == 0:
        return {}

    axes = {
        "x": _moving_average(x[:frame_count].tolist(), 9),
        "y": _moving_average(y[:frame_count].tolist(), 9),
    }
    motion = np.asarray(signals.motion[:frame_count], dtype=float)
    if len(motion) < frame_count:
        motion = np.pad(motion, (0, frame_count - len(motion)), mode="constant")
    baseline_frame_count = max(15, min(45, frame_count // 8))
    baselines = {
        axis: _axis_baseline(values, baseline_frame_count)
        for axis, values in axes.items()
    }
    detected = detected[:frame_count]

    candidates: dict[str, DirectionCandidate] = {}
    search_start = 0
    for direction, axis, sign, minimum_threshold in EXPECTED_DIRECTION_SEQUENCE:
        candidate = _first_ordered_direction_candidate(
            direction=direction,
            axis=axis,
            sign=sign,
            values=axes[axis],
            detected=detected,
            search_start=search_start,
            minimum_threshold=minimum_threshold,
            baseline=baselines[axis][0],
            baseline_noise=baselines[axis][1],
            motion=motion,
        )
        if candidate is not None:
            candidates[direction] = candidate
            search_start = candidate.motion_end + 1

    return candidates


def build_proposed_marks(
    total_frames: int,
    signals: FrameSignals,
    candidates: dict[str, DirectionCandidate],
) -> dict[str, ProposedMark]:
    proposed: dict[str, ProposedMark] = {}
    first_motion_start = min((candidate.motion_start for candidate in candidates.values()), default=None)
    if first_motion_start is not None and first_motion_start >= 15:
        proposed["CENTER_IDLE"] = ProposedMark(
            name="CENTER_IDLE",
            start_frame=0,
            end_frame=max(14, first_motion_start - 1),
            confidence=_center_idle_confidence(signals, first_motion_start),
            source="initial stable center before first detected movement",
        )
    else:
        proposed["CENTER_IDLE"] = ProposedMark(
            name="CENTER_IDLE",
            start_frame=None,
            end_frame=None,
            confidence=0.15,
            source="initial stable center before first detected movement",
            warnings=("not enough stable center frames before first motion",),
        )

    for direction, candidate in candidates.items():
        transition_name, idle_name, return_name = DIRECTION_TO_SEGMENTS[direction]
        transition_in, idle, transition_out = _partition_candidate(candidate, total_frames)

        proposed[transition_name] = _make_mark(
            transition_name,
            transition_in,
            max(0.05, candidate.confidence - 0.08),
            f"{direction} movement start",
            minimum_frames=3,
        )
        proposed[idle_name] = _make_mark(
            idle_name,
            idle,
            candidate.confidence,
            f"{direction} stable hold",
            minimum_frames=15,
        )
        proposed[return_name] = _make_mark(
            return_name,
            transition_out,
            max(0.05, candidate.confidence - 0.08),
            f"{direction} return to center",
            minimum_frames=3,
        )

    for name in REQUIRED_SEGMENTS:
        proposed.setdefault(
            name,
            ProposedMark(
                name=name,
                start_frame=None,
                end_frame=None,
                confidence=0.0,
                source="not detected",
                warnings=("automatic detector did not find a confident candidate",),
            ),
        )
    return proposed


def build_report(
    video_path: Path,
    metadata: VideoMetadata,
    signals: FrameSignals,
    candidates: dict[str, DirectionCandidate],
    proposed_marks: dict[str, ProposedMark],
) -> dict[str, Any]:
    undetected = [
        name
        for name in REQUIRED_SEGMENTS
        if proposed_marks[name].start_frame is None or proposed_marks[name].end_frame is None
    ]
    low_confidence = [
        name
        for name in REQUIRED_SEGMENTS
        if proposed_marks[name].confidence < 0.55
        and proposed_marks[name].start_frame is not None
        and proposed_marks[name].end_frame is not None
    ]
    warnings = list(signals.warnings)
    if undetected:
        warnings.append("Some required segments were left as null because confidence was too low.")
    if low_confidence:
        warnings.append("Some detected segments have low confidence and need careful visual review.")

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "video_path": str(video_path),
        "video": {
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "total_frames": metadata.frame_count,
            "duration_seconds": metadata.duration_seconds,
            "codec": metadata.codec,
            "orientation_degrees": metadata.orientation_degrees,
        },
        "method": {
            "name": signals.method,
            "face_detection_coverage": round(_mean_bool(signals.face_detected), 4),
            "frame_motion_metric": "mean absolute grayscale frame difference",
            "note": "Draft heuristic only; visual manual review is required.",
        },
        "candidate_frames": {
            direction: candidate.to_report() for direction, candidate in candidates.items()
        },
        "segments": {
            name: proposed_marks[name].to_report() for name in REQUIRED_SEGMENTS
        },
        "undetected_segments": undetected,
        "low_confidence_segments": low_confidence,
        "warnings": warnings,
        "manual_review_recommendation": (
            "Open config/segments.auto.yaml with tools/preview_segments.py, then copy or "
            "adjust marks into config/segments.yaml using tools/mark_segments.py."
        ),
    }


def save_auto_report(path: Path | str, report: dict[str, Any]) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return report_path


def _collect_mediapipe_signals(
    video_path: Path,
    metadata: VideoMetadata,
    analysis_width: int,
) -> FrameSignals | None:
    try:
        import cv2
        import mediapipe as mp
    except ModuleNotFoundError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise VideoIOError(f"OpenCV could not open video: {video_path}")

    x_values: list[float | None] = []
    y_values: list[float | None] = []
    detected: list[bool] = []
    motion: list[float] = []
    previous_gray: Any | None = None
    analysis_height = max(1, int(round(metadata.height * analysis_width / metadata.width)))

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            small = cv2.resize(frame, (analysis_width, analysis_height))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            motion.append(_frame_motion(gray, previous_gray))
            previous_gray = gray

            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                nose = landmarks[1]
                x_values.append(float(nose.x * analysis_width))
                y_values.append(float(nose.y * analysis_height))
                detected.append(True)
            else:
                x_values.append(None)
                y_values.append(None)
                detected.append(False)
    finally:
        face_mesh.close()
        capture.release()

    if _mean_bool(detected) < 0.35:
        return None

    return FrameSignals(
        x=_moving_average(_fill_missing(x_values, analysis_width / 2.0), 7),
        y=_moving_average(_fill_missing(y_values, analysis_height / 2.0), 7),
        motion=_moving_average(motion, 5),
        face_detected=detected,
        method="mediapipe_face_mesh_nose_landmark",
        warnings=[],
    )


def _collect_haar_signals(
    video_path: Path,
    metadata: VideoMetadata,
    analysis_width: int,
) -> FrameSignals:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise VideoIOError(
            "OpenCV is not installed. Run: python -m pip install opencv-python"
        ) from exc

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise VideoIOError(f"OpenCV could not open video: {video_path}")

    analysis_height = max(1, int(round(metadata.height * analysis_width / metadata.width)))
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if face.empty():
        raise VideoIOError("OpenCV Haar frontal face cascade could not be loaded.")

    x_values: list[float | None] = []
    y_values: list[float | None] = []
    detected: list[bool] = []
    motion: list[float] = []
    previous_gray: Any | None = None
    warnings: list[str] = []

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            small = cv2.resize(frame, (analysis_width, analysis_height))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            equalized = cv2.equalizeHist(gray)
            motion.append(_frame_motion(gray, previous_gray))
            previous_gray = gray

            faces = list(
                face.detectMultiScale(
                    equalized,
                    scaleFactor=1.1,
                    minNeighbors=4,
                    minSize=(max(40, analysis_width // 12), max(40, analysis_height // 12)),
                )
            )
            if faces:
                x, y, w, h = _choose_face_box(faces, analysis_width, analysis_height)
                x_values.append(float(x + w / 2.0))
                y_values.append(float(y + h / 2.0))
                detected.append(True)
            else:
                x_values.append(None)
                y_values.append(None)
                detected.append(False)
    finally:
        capture.release()

    coverage = _mean_bool(detected)
    if coverage < 0.5:
        warnings.append(
            f"OpenCV face detection coverage is low ({coverage:.2%}); proposal may be incomplete."
        )

    return FrameSignals(
        x=_moving_average(_fill_missing(x_values, analysis_width / 2.0), 9),
        y=_moving_average(_fill_missing(y_values, analysis_height / 2.0), 9),
        motion=_moving_average(motion, 5),
        face_detected=detected,
        method="opencv_haar_largest_face",
        warnings=warnings,
    )


def _first_ordered_direction_candidate(
    direction: str,
    axis: str,
    sign: int,
    values: list[float],
    detected: np.ndarray,
    search_start: int,
    minimum_threshold: float,
    baseline: float,
    baseline_noise: float,
    motion: np.ndarray,
) -> DirectionCandidate | None:
    """Find the next complete out/hold/return cycle on the expected axis.

    The recording protocol provides the direction semantics, so Haar's coordinate
    sign is deliberately not used. The first complete absolute excursion after
    the previous return is assigned to the next protocol direction.
    """
    if search_start >= len(values):
        return None

    array = np.asarray(values, dtype=float)
    offsets = np.abs(array - baseline)
    excursion_threshold = max(minimum_threshold, baseline_noise * 4.0)
    excursion_runs = _runs(offsets >= excursion_threshold, min_length=15, merge_gap=4)
    excursion_runs = [run for run in excursion_runs if run[0] >= search_start]
    if not excursion_runs:
        return None

    # The first sustained excursion is the action prescribed by the protocol. If
    # it never returns to the neutral center, do not skip ahead and relabel a later
    # action as the missing direction.
    excursion_start, excursion_end = excursion_runs[0]
    peak_slice = offsets[excursion_start : excursion_end + 1]
    peak_rel = int(np.argmax(peak_slice))
    peak_frame = excursion_start + peak_rel
    peak_offset = float(peak_slice[peak_rel])
    threshold = max(excursion_threshold, peak_offset * 0.38)
    refined_runs = _runs(offsets >= threshold, min_length=15, merge_gap=4)
    refined_runs = [
        run
        for run in refined_runs
        if run[0] >= excursion_start
        and run[1] <= excursion_end
        and run[0] <= peak_frame <= run[1]
    ]
    if not refined_runs:
        return None
    hold_start, hold_end = refined_runs[0]
    return_threshold = max(
        2.0,
        excursion_threshold * 0.35,
        baseline_noise * 2.5,
        peak_offset * 0.3,
    )
    return_start = _first_sustained_return(
        offsets,
        start=max(hold_end + 3, excursion_end + 1),
        threshold=return_threshold,
        minimum_frames=5,
    )
    if return_start is None:
        return None

    departure_threshold = max(1.0, excursion_threshold * 0.2, baseline_noise * 1.5)
    motion_start = excursion_start
    while motion_start > search_start and offsets[motion_start - 1] > departure_threshold:
        motion_start -= 1
    motion_start = _refine_transition_start_from_motion(
        motion,
        search_start=search_start,
        axis_start=motion_start,
        hold_start=hold_start,
    )

    motion_end = return_start
    coverage = float(np.mean(detected[motion_start : motion_end + 1]))
    duration = motion_end - motion_start + 1
    hold_duration = hold_end - hold_start + 1
    confidence = _candidate_confidence(
        peak_offset,
        threshold,
        coverage,
        duration,
        hold_duration,
    )
    warnings: list[str] = []
    if coverage < 0.7:
        warnings.append(
            "face tracking coverage is limited; ordered position signals were used anyway"
        )

    return DirectionCandidate(
        direction=direction,
        axis=axis,
        sign=sign,
        motion_start=motion_start,
        hold_start=hold_start,
        hold_end=hold_end,
        motion_end=motion_end,
        peak_frame=peak_frame,
        peak_offset=peak_offset,
        threshold=threshold,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def _refine_transition_start_from_motion(
    motion: np.ndarray,
    search_start: int,
    axis_start: int,
    hold_start: int,
) -> int:
    transition_span = hold_start - axis_start
    if transition_span < 4 or transition_span > 45:
        return axis_start

    baseline_start = max(search_start, axis_start - 24)
    baseline_sample = motion[baseline_start:axis_start]
    if len(baseline_sample) < 5:
        return axis_start
    baseline = float(np.median(baseline_sample))
    noise = float(np.median(np.abs(baseline_sample - baseline)))
    activity_threshold = baseline + max(0.25, noise * 3.0)

    for index in range(axis_start, hold_start - 2):
        window = motion[index : index + 3]
        if len(window) == 3 and float(np.mean(window)) >= activity_threshold:
            return index
    return axis_start


def _axis_baseline(values: list[float], frame_count: int) -> tuple[float, float]:
    sample = np.asarray(values[:frame_count], dtype=float)
    if len(sample) == 0:
        return 0.0, 0.0
    baseline = float(np.median(sample))
    noise = float(np.median(np.abs(sample - baseline)))
    return baseline, noise


def _first_sustained_return(
    offsets: np.ndarray,
    start: int,
    threshold: float,
    minimum_frames: int,
) -> int | None:
    last_start = len(offsets) - minimum_frames
    for index in range(start, last_start + 1):
        if bool(np.all(offsets[index : index + minimum_frames] <= threshold)):
            return index
    return None


def _partition_candidate(
    candidate: DirectionCandidate,
    total_frames: int,
) -> tuple[tuple[int, int] | None, tuple[int, int] | None, tuple[int, int] | None]:
    del total_frames
    transition_in = (candidate.motion_start, candidate.hold_start - 1)
    if _frame_count(transition_in) < 3:
        transition_in = None

    idle = (candidate.hold_start, candidate.hold_end)
    if _frame_count(idle) < 15:
        idle = None

    transition_out = (candidate.hold_end + 1, candidate.motion_end)
    if _frame_count(transition_out) < 3:
        transition_out = None
    return transition_in, idle, transition_out


def _make_mark(
    name: str,
    frame_range: tuple[int, int] | None,
    confidence: float,
    source: str,
    minimum_frames: int,
) -> ProposedMark:
    if frame_range is None:
        return ProposedMark(
            name=name,
            start_frame=None,
            end_frame=None,
            confidence=min(confidence, 0.25),
            source=source,
            warnings=(f"could not find at least {minimum_frames} compatible frames",),
        )

    start_frame, end_frame = frame_range
    count = end_frame - start_frame + 1
    warnings: list[str] = []
    if count < minimum_frames:
        warnings.append(f"shorter than requested minimum of {minimum_frames} frames")
    return ProposedMark(
        name=name,
        start_frame=start_frame,
        end_frame=end_frame,
        confidence=round(confidence, 4),
        source=source,
        warnings=tuple(warnings),
    )


def _choose_face_box(faces: list[Any], width: int, height: int) -> tuple[int, int, int, int]:
    center_x = width * 0.5
    center_y = height * 0.48
    best_score = -1.0
    best_box = tuple(int(value) for value in faces[0])
    for raw_box in faces:
        x, y, w, h = (int(value) for value in raw_box)
        area = float(w * h)
        box_center_x = x + w / 2.0
        box_center_y = y + h / 2.0
        center_penalty = abs(box_center_x - center_x) / width + abs(box_center_y - center_y) / height
        score = area / (1.0 + center_penalty)
        if score > best_score:
            best_score = score
            best_box = (x, y, w, h)
    return best_box


def _runs(mask: np.ndarray, min_length: int, merge_gap: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(mask.tolist()):
        if active and start is None:
            start = index
        elif not active and start is not None:
            if index - start >= min_length:
                runs.append((start, index - 1))
            start = None
    if start is not None and len(mask) - start >= min_length:
        runs.append((start, len(mask) - 1))

    if not runs:
        return []

    merged = [runs[0]]
    for start, end in runs[1:]:
        last_start, last_end = merged[-1]
        if start - last_end - 1 <= merge_gap:
            merged[-1] = (last_start, end)
        else:
            merged.append((start, end))
    return merged


def _candidate_confidence(
    peak_offset: float,
    threshold: float,
    coverage: float,
    duration: int,
    hold_duration: int,
) -> float:
    peak_score = min(1.0, peak_offset / max(threshold * 1.8, 1.0))
    duration_score = min(1.0, duration / 25.0)
    hold_score = min(1.0, hold_duration / 18.0)
    confidence = 0.2 + 0.35 * peak_score + 0.25 * coverage + 0.1 * duration_score + 0.1 * hold_score
    return round(max(0.0, min(0.95, confidence)), 4)


def _center_idle_confidence(signals: FrameSignals, end_exclusive: int) -> float:
    if end_exclusive <= 0:
        return 0.1
    coverage = _mean_bool(signals.face_detected[:end_exclusive])
    duration_score = min(1.0, end_exclusive / 30.0)
    motion = np.asarray(signals.motion[:end_exclusive], dtype=float)
    motion_score = 0.8
    if len(motion) > 0:
        median_motion = float(np.median(signals.motion))
        if median_motion > 0:
            motion_score = max(0.0, min(1.0, 1.2 - float(np.mean(motion)) / median_motion))
    return round(min(0.95, 0.25 + 0.35 * coverage + 0.25 * duration_score + 0.15 * motion_score), 4)


def _frame_count(frame_range: tuple[int, int] | None) -> int:
    if frame_range is None:
        return 0
    return frame_range[1] - frame_range[0] + 1


def _frame_motion(gray: Any, previous_gray: Any | None) -> float:
    if previous_gray is None:
        return 0.0
    import cv2

    return float(np.mean(cv2.absdiff(gray, previous_gray)))


def _fill_missing(values: list[float | None], default: float) -> list[float]:
    if not values:
        return []
    numeric = np.asarray([np.nan if value is None else float(value) for value in values], dtype=float)
    valid = ~np.isnan(numeric)
    if not np.any(valid):
        return [default for _ in values]
    indices = np.arange(len(values))
    filled = np.interp(indices, indices[valid], numeric[valid])
    return filled.astype(float).tolist()


def _moving_average(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    if window <= 1:
        return [float(value) for value in values]
    array = np.asarray(values, dtype=float)
    output: list[float] = []
    half = window // 2
    for index in range(len(array)):
        start = max(0, index - half)
        end = min(len(array), index + half + 1)
        output.append(float(np.mean(array[start:end])))
    return output


def _mean_bool(values: list[bool] | np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    return float(np.mean(np.asarray(values, dtype=bool)))
