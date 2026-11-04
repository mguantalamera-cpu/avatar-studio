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

from avatar_controller.config import ConfigError, load_config, validate_video_path  # noqa: E402
from avatar_controller.segments import (  # noqa: E402
    KNOWN_SEGMENTS,
    SegmentError,
    SegmentMark,
    SegmentSet,
    create_empty_segment_set,
    load_segments,
    save_segments,
    validate_segments,
)
from avatar_controller.video_io import VideoIOError, read_video_metadata  # noqa: E402


WINDOW_NAME = "Avatar Segment Marker"


@dataclass
class EditorState:
    segment_set: SegmentSet
    current_frame: int = 0
    selected_index: int = 0
    playing: bool = False
    show_help: bool = True
    status_message: str = "Ready"

    @property
    def selected_name(self) -> str:
        return KNOWN_SEGMENTS[self.selected_index]

    @property
    def selected_segment(self) -> SegmentMark:
        return self.segment_set.segments[self.selected_name]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manually mark avatar video segments.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--segments", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Load inputs and exit without UI.")
    args = parser.parse_args(argv)

    segments_path = args.segments or args.config.parent / "segments.yaml"

    try:
        app_config = load_config(args.config)
        video_path = validate_video_path(app_config.video.path)
        metadata = read_video_metadata(video_path)
        segment_set = load_or_create_segment_set(segments_path, video_path, metadata)

        if args.dry_run:
            result = validate_segments(segment_set, metadata.frame_count)
            print(f"Video: {video_path}")
            print(f"Segments: {segments_path}")
            print(f"Validation: {len(result.errors)} errors, {len(result.warnings)} warnings")
            return 0

        cv2 = _load_cv2()
        return run_editor(cv2, video_path, segments_path, segment_set)
    except (ConfigError, SegmentError, VideoIOError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def load_or_create_segment_set(
    segments_path: Path,
    video_path: Path,
    metadata: Any,
) -> SegmentSet:
    if segments_path.exists():
        segment_set = load_segments(segments_path)
        ensure_required_segments(segment_set)
        return segment_set
    return create_empty_segment_set(video_path, metadata)


def ensure_required_segments(segment_set: SegmentSet) -> None:
    for name in KNOWN_SEGMENTS:
        segment_set.segments.setdefault(name, SegmentMark(name=name))


def run_editor(cv2: Any, video_path: Path, segments_path: Path, segment_set: SegmentSet) -> int:
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoIOError(f"OpenCV could not open video: {video_path}")

        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or segment_set.fps or 30.0
        frame_delay_ms = max(1, int(round(1000.0 / fps)))
        state = EditorState(segment_set=segment_set)

        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        last_tick = time.perf_counter()

        while True:
            frame = read_frame(cv2, capture, state.current_frame)
            display = draw_overlay(cv2, frame, state, video_path, fps, total_frames)
            cv2.imshow(WINDOW_NAME, display)

            wait_ms = frame_delay_ms if state.playing else 30
            key = cv2.waitKey(wait_ms) & 0xFF
            if key != 255:
                action = handle_key(
                    cv2, capture, key, state, segments_path, video_path, fps, total_frames
                )
                if action == "quit":
                    break
                last_tick = time.perf_counter()
                continue

            if state.playing:
                now = time.perf_counter()
                if now - last_tick >= 1.0 / fps:
                    state.current_frame = clamp_frame(state.current_frame + 1, total_frames)
                    last_tick = now

        return 0
    finally:
        capture.release()
        cv2.destroyAllWindows()


def handle_key(
    cv2: Any,
    capture: Any,
    key: int,
    state: EditorState,
    segments_path: Path,
    video_path: Path,
    fps: float,
    total_frames: int,
) -> str | None:
    char = chr(key).lower() if 0 <= key < 256 else ""

    if key == 27 or char == "q":
        return "quit"
    if char == "a":
        state.current_frame = clamp_frame(state.current_frame - 1, total_frames)
        state.playing = False
    elif char == "d":
        state.current_frame = clamp_frame(state.current_frame + 1, total_frames)
        state.playing = False
    elif char == "j":
        state.current_frame = clamp_frame(state.current_frame - 10, total_frames)
        state.playing = False
    elif char == "l":
        state.current_frame = clamp_frame(state.current_frame + 10, total_frames)
        state.playing = False
    elif char == "k":
        state.current_frame = clamp_frame(state.current_frame - 30, total_frames)
        state.playing = False
    elif char == "o":
        state.current_frame = clamp_frame(state.current_frame + 30, total_frames)
        state.playing = False
    elif key == ord(" "):
        state.playing = not state.playing
        state.status_message = "Playing" if state.playing else "Paused"
    elif key == ord("["):
        state.selected_segment.start_frame = state.current_frame
        state.status_message = f"Set start for {state.selected_name}: {state.current_frame}"
    elif key == ord("]"):
        state.selected_segment.end_frame = state.current_frame
        state.status_message = f"Set end for {state.selected_name}: {state.current_frame}"
    elif char == "n":
        state.selected_index = (state.selected_index + 1) % len(KNOWN_SEGMENTS)
        state.status_message = f"Selected {state.selected_name}"
    elif char == "p":
        state.selected_index = (state.selected_index - 1) % len(KNOWN_SEGMENTS)
        state.status_message = f"Selected {state.selected_name}"
    elif char == "s":
        save_segments(segments_path, state.segment_set)
        result = validate_segments(state.segment_set, total_frames)
        state.status_message = (
            f"Saved {segments_path.name}: {len(result.errors)} errors, "
            f"{len(result.warnings)} warnings"
        )
        print_validation_summary(result)
    elif char == "v":
        play_selected_segment(cv2, capture, state, video_path, fps, loop=False)
    elif char == "b":
        play_selected_segment(cv2, capture, state, video_path, fps, loop=True)
    elif char == "c":
        state.selected_segment.start_frame = None
        state.selected_segment.end_frame = None
        state.selected_segment.notes = ""
        state.status_message = f"Cleared {state.selected_name}"
    elif char == "h":
        state.show_help = not state.show_help

    return None


def play_selected_segment(
    cv2: Any,
    capture: Any,
    state: EditorState,
    video_path: Path,
    fps: float,
    loop: bool,
) -> None:
    segment = state.selected_segment
    if segment.start_frame is None or segment.end_frame is None:
        state.status_message = f"{segment.name} is incomplete"
        return
    if segment.start_frame > segment.end_frame:
        state.status_message = f"{segment.name} is invalid"
        return

    delay_ms = max(1, int(round(1000.0 / fps)))
    original_frame = state.current_frame
    stop = False
    while not stop:
        for frame_index in range(segment.start_frame, segment.end_frame + 1):
            frame = read_frame(cv2, capture, frame_index)
            state.current_frame = frame_index
            display = draw_overlay(cv2, frame, state, video_path, fps, state.segment_set.total_frames)
            cv2.putText(
                display,
                "PREVIEW LOOP - ESC/Q stops" if loop else "PREVIEW ONCE",
                (24, display.shape[0] - 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(WINDOW_NAME, display)
            key = cv2.waitKey(delay_ms) & 0xFF
            if key in {27, ord("q"), ord("Q")}:
                stop = True
                break
        if not loop:
            break
    state.current_frame = original_frame
    state.status_message = f"Previewed {segment.name}"


def read_frame(cv2: Any, capture: Any, frame_index: int) -> Any:
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok or frame is None:
        raise VideoIOError(f"Could not read frame {frame_index}")
    return frame


def draw_overlay(
    cv2: Any,
    frame: Any,
    state: EditorState,
    video_path: Path,
    fps: float,
    total_frames: int,
) -> Any:
    display = frame.copy()
    panel = display.copy()
    height, width = display.shape[:2]
    panel_height = 330 if state.show_help else 205
    cv2.rectangle(panel, (0, 0), (min(width, 980), panel_height), (0, 0, 0), -1)
    display = cv2.addWeighted(panel, 0.56, display, 0.44, 0)

    segment = state.selected_segment
    status = segment_status(state.segment_set, segment, total_frames)
    if segment.frame_count is not None and fps > 0:
        duration = f"{segment.frame_count} frames / {segment.frame_count / fps:.2f}s"
    else:
        duration = "n/a"

    lines = [
        f"Video: {video_path.name}",
        f"Frame: {state.current_frame}/{total_frames - 1}   Time: {state.current_frame / fps:.2f}s   FPS: {fps:.4f}",
        f"Segment: {state.selected_index + 1}/{len(KNOWN_SEGMENTS)} {state.selected_name}",
        f"Start: {segment.start_frame}   End: {segment.end_frame}   Duration: {duration}",
        f"Status: {status}",
        f"Mode: {'PLAY' if state.playing else 'PAUSE'}   Last: {state.status_message}",
    ]

    if state.show_help:
        lines.extend(
            [
                "A/D prev/next  J/L +/-10  K/O +/-30  SPACE play/pause",
                "[ set start   ] set end   N/P segment   S save   C clear",
                "V preview once   B loop selected   H hide help   Q/ESC quit",
            ]
        )

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


def segment_status(segment_set: SegmentSet, segment: SegmentMark, total_frames: int) -> str:
    if segment.start_frame is None or segment.end_frame is None:
        return "INCOMPLETE"
    result = validate_segments(segment_set, total_frames)
    selected_errors = [issue.format() for issue in result.errors if issue.segment == segment.name]
    if selected_errors:
        return "INVALID - " + selected_errors[0].split(": ", 1)[-1]
    selected_warnings = [issue.format() for issue in result.warnings if issue.segment == segment.name]
    if selected_warnings:
        return "COMPLETE WITH WARNING"
    return "COMPLETE"


def status_color(status: str) -> tuple[int, int, int]:
    if status.startswith("COMPLETE WITH WARNING"):
        return (0, 220, 255)
    if status.startswith("COMPLETE"):
        return (0, 220, 0)
    if status.startswith("INVALID"):
        return (0, 0, 255)
    return (0, 255, 255)


def print_validation_summary(result: Any) -> None:
    if result.errors:
        print("Segment validation errors:")
        for issue in result.errors:
            print(f"  - {issue.format()}")
    if result.warnings:
        print("Segment validation warnings:")
        for issue in result.warnings:
            print(f"  - {issue.format()}")
    if not result.errors and not result.warnings:
        print("All segments are valid.")


def clamp_frame(frame_index: int, total_frames: int) -> int:
    return max(0, min(total_frames - 1, frame_index))


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
