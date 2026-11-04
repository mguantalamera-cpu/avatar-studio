from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from avatar_controller.config import ConfigError, load_config, validate_video_path
from avatar_controller.segments import (
    REQUIRED_SEGMENTS,
    SegmentError,
    SegmentMark,
    SegmentSet,
    load_segments,
    validate_segments,
)
from avatar_controller.video_io import VideoIOError, read_video_metadata


WINDOW_NAME = "Avatar Segment Preview"


@dataclass
class PreviewState:
    segment_set: SegmentSet
    selected_index: int = 0
    show_help: bool = True
    status_message: str = "Ready"

    @property
    def selected_name(self) -> str:
        return REQUIRED_SEGMENTS[self.selected_index]

    @property
    def selected_segment(self) -> SegmentMark | None:
        return self.segment_set.segments.get(self.selected_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview manual or auto-marked avatar video segments.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--list-only", action="store_true", help="Print segment status and exit.")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier for V/B preview. 1.0 is real time.",
    )
    args = parser.parse_args(argv)

    try:
        if args.speed <= 0:
            raise ConfigError("--speed must be greater than 0.")

        app_config = load_config(args.config)
        video_path = validate_video_path(app_config.video.path)
        metadata = read_video_metadata(video_path)
        segment_set = load_segments(args.segments)
        result = validate_segments(segment_set, metadata.frame_count)
        print_segment_status(segment_set, metadata.frame_count)
        print(f"Validation: {len(result.errors)} errors, {len(result.warnings)} warnings")

        if args.list_only:
            return 0

        cv2 = _load_cv2()
        return run_preview(cv2, video_path, segment_set, speed=args.speed)
    except (ConfigError, SegmentError, VideoIOError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_preview(cv2: Any, video_path: Path, segment_set: SegmentSet, speed: float = 1.0) -> int:
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoIOError(f"OpenCV could not open video: {video_path}")

        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or segment_set.fps or 30.0
        state = PreviewState(segment_set=segment_set)
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

        while True:
            frame_index = display_frame_for_segment(state.selected_segment, total_frames)
            frame = read_frame(cv2, capture, frame_index)
            display = draw_overlay(cv2, frame, state, video_path, fps, frame_index, total_frames)
            cv2.imshow(WINDOW_NAME, display)
            key = cv2.waitKey(30) & 0xFF
            action = handle_key(cv2, capture, key, state, video_path, fps, total_frames, speed)
            if action == "quit":
                break
        return 0
    finally:
        capture.release()
        cv2.destroyAllWindows()


def handle_key(
    cv2: Any,
    capture: Any,
    key: int,
    state: PreviewState,
    video_path: Path,
    fps: float,
    total_frames: int,
    speed: float,
) -> str | None:
    if key == 255:
        return None
    char = chr(key).lower() if 0 <= key < 256 else ""
    if key == 27 or char == "q":
        return "quit"
    if char == "n":
        state.selected_index = (state.selected_index + 1) % len(REQUIRED_SEGMENTS)
        state.status_message = f"Selected {state.selected_name}"
    elif char == "p":
        state.selected_index = (state.selected_index - 1) % len(REQUIRED_SEGMENTS)
        state.status_message = f"Selected {state.selected_name}"
    elif char == "v":
        play_segment(cv2, capture, state, video_path, fps, total_frames, loop=False, speed=speed)
    elif char == "b":
        play_segment(cv2, capture, state, video_path, fps, total_frames, loop=True, speed=speed)
    elif char == "h":
        state.show_help = not state.show_help
    return None


def play_segment(
    cv2: Any,
    capture: Any,
    state: PreviewState,
    video_path: Path,
    fps: float,
    total_frames: int,
    loop: bool,
    speed: float = 1.0,
) -> None:
    segment = state.selected_segment
    if segment is None or segment.start_frame is None or segment.end_frame is None:
        state.status_message = f"{state.selected_name} is incomplete"
        return
    if segment.start_frame > segment.end_frame:
        state.status_message = f"{state.selected_name} is invalid"
        return

    frame_delay_seconds = frame_delay_for_fps(fps, speed)
    stop = False
    while not stop:
        seek_frame(cv2, capture, segment.start_frame)
        next_frame_time = time.perf_counter()
        for frame_index in range(segment.start_frame, segment.end_frame + 1):
            frame = read_current_frame(capture, frame_index)
            display = draw_overlay(cv2, frame, state, video_path, fps, frame_index, total_frames)
            cv2.putText(
                display,
                "LOOP - ESC/Q stops" if loop else "PLAY ONCE",
                (24, display.shape[0] - 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(WINDOW_NAME, display)
            next_frame_time += frame_delay_seconds
            key = cv2.waitKey(wait_ms_until(next_frame_time)) & 0xFF
            if key in {27, ord("q"), ord("Q")}:
                stop = True
                break
            if time.perf_counter() - next_frame_time > frame_delay_seconds:
                next_frame_time = time.perf_counter()
        if not loop:
            break
    state.status_message = f"Previewed {state.selected_name}"


def display_frame_for_segment(segment: SegmentMark | None, total_frames: int) -> int:
    if segment is None or segment.start_frame is None:
        return 0
    return max(0, min(total_frames - 1, segment.start_frame))


def read_frame(cv2: Any, capture: Any, frame_index: int) -> Any:
    seek_frame(cv2, capture, frame_index)
    return read_current_frame(capture, frame_index)


def seek_frame(cv2: Any, capture: Any, frame_index: int) -> None:
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)


def read_current_frame(capture: Any, frame_index: int) -> Any:
    ok, frame = capture.read()
    if not ok or frame is None:
        raise VideoIOError(f"Could not read frame {frame_index}")
    return frame


def frame_delay_for_fps(fps: float, speed: float = 1.0) -> float:
    if fps <= 0:
        raise ValueError("fps must be greater than 0")
    if speed <= 0:
        raise ValueError("speed must be greater than 0")
    return 1.0 / (fps * speed)


def delay_ms_for_fps(fps: float, speed: float = 1.0) -> int:
    return max(1, int(round(frame_delay_for_fps(fps, speed) * 1000.0)))


def wait_ms_until(target_time: float) -> int:
    remaining_seconds = target_time - time.perf_counter()
    if remaining_seconds <= 0:
        return 1
    return max(1, int(round(remaining_seconds * 1000.0)))


def draw_overlay(
    cv2: Any,
    frame: Any,
    state: PreviewState,
    video_path: Path,
    fps: float,
    frame_index: int,
    total_frames: int,
) -> Any:
    display = frame.copy()
    panel = display.copy()
    panel_height = 275 if state.show_help else 175
    cv2.rectangle(panel, (0, 0), (min(display.shape[1], 920), panel_height), (0, 0, 0), -1)
    display = cv2.addWeighted(panel, 0.56, display, 0.44, 0)

    segment = state.selected_segment
    status = segment_status(state.segment_set, state.selected_name, total_frames)
    start = segment.start_frame if segment else None
    end = segment.end_frame if segment else None
    if segment and segment.frame_count is not None and fps > 0:
        duration = f"{segment.frame_count} frames / {segment.frame_count / fps:.2f}s"
    else:
        duration = "n/a"

    lines = [
        f"Video: {video_path.name}",
        f"Frame: {frame_index}/{total_frames - 1}   Time: {frame_index / fps:.2f}s   FPS: {fps:.4f}",
        f"Segment: {state.selected_index + 1}/{len(REQUIRED_SEGMENTS)} {state.selected_name}",
        f"Start: {start}   End: {end}   Duration: {duration}",
        f"Status: {status}   Last: {state.status_message}",
    ]
    if state.show_help:
        lines.extend(["N/P segment   V play once   B loop selected   H hide help   Q/ESC quit"])

    y = 32
    for index, line in enumerate(lines):
        color = (255, 255, 255)
        if index == 4:
            color = status_color(status)
        cv2.putText(
            display,
            line,
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            color,
            2,
            cv2.LINE_AA,
        )
        y += 34
    return display


def segment_status(segment_set: SegmentSet, segment_name: str, total_frames: int) -> str:
    segment = segment_set.segments.get(segment_name)
    if segment is None:
        return "MISSING"
    if segment.start_frame is None or segment.end_frame is None:
        return "INCOMPLETE"
    result = validate_segments(segment_set, total_frames)
    selected_errors = [issue for issue in result.errors if issue.segment == segment_name]
    if selected_errors:
        return "INVALID - " + selected_errors[0].message
    selected_warnings = [issue for issue in result.warnings if issue.segment == segment_name]
    if selected_warnings:
        return "COMPLETE WITH WARNING"
    return "COMPLETE"


def status_color(status: str) -> tuple[int, int, int]:
    if status.startswith("COMPLETE WITH WARNING"):
        return (0, 220, 255)
    if status.startswith("COMPLETE"):
        return (0, 220, 0)
    if status.startswith("INVALID") or status == "MISSING":
        return (0, 0, 255)
    return (0, 255, 255)


def print_segment_status(segment_set: SegmentSet, total_frames: int) -> None:
    for name in REQUIRED_SEGMENTS:
        segment = segment_set.segments.get(name)
        status = segment_status(segment_set, name, total_frames)
        if segment is None:
            print(f"{name}: MISSING")
            continue
        print(f"{name}: {status} ({segment.start_frame}-{segment.end_frame})")


def _load_cv2() -> Any:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise VideoIOError(
            "OpenCV is not installed. Run: python -m pip install opencv-python"
        ) from exc
    return cv2


if __name__ == "__main__":
    raise SystemExit(main())
